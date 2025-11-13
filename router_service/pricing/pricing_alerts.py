"""Pricing alert management and notification system."""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

import aiohttp

from .pricing_config import PricingConfig

logger = logging.getLogger(__name__)


class PricingAlertManager:
    """Manager for pricing alerts and notifications."""
    
    def __init__(self, config: PricingConfig):
        self.config = config
        
        # Alert state tracking
        self._alert_count = 0
        self._last_alert_times: Dict[str, float] = {}
        self._alert_cooldown = 300  # 5 minutes between similar alerts
    
    async def send_pricing_alert(
        self,
        provider: str,
        model: str,
        change_data: Dict[str, Any],
        severity: str = "medium"
    ) -> bool:
        """Send pricing change alert."""
        if not self.config.alerts_enabled:
            return False
        
        # Check cooldown
        alert_key = f"{provider}:{model}:{severity}"
        if self._is_in_cooldown(alert_key):
            return False
        
        alert_data = {
            "type": "pricing_change",
            "severity": severity,
            "provider": provider,
            "model": model,
            "change_data": change_data,
            "timestamp": change_data.get("detected_at"),
            "message": self._format_pricing_change_message(provider, model, change_data, severity)
        }
        
        success = await self._send_alert(alert_data)
        
        if success:
            self._update_alert_tracking(alert_key)
        
        return success
    
    async def send_staleness_alert(
        self,
        stale_items: List[Dict[str, Any]],
        severity: str = "low"
    ) -> bool:
        """Send alert for stale pricing data."""
        if not self.config.alerts_enabled or not stale_items:
            return False
        
        alert_key = "staleness"
        if self._is_in_cooldown(alert_key):
            return False
        
        alert_data = {
            "type": "pricing_staleness",
            "severity": severity,
            "stale_count": len(stale_items),
            "stale_items": stale_items,
            "message": self._format_staleness_message(stale_items)
        }
        
        success = await self._send_alert(alert_data)
        
        if success:
            self._update_alert_tracking(alert_key)
        
        return success
    
    async def send_validation_alert(
        self,
        validation_result: Dict[str, Any],
        severity: str = "medium"
    ) -> bool:
        """Send alert for pricing validation failures."""
        if not self.config.alerts_enabled:
            return False
        
        provider = validation_result.get("provider", "unknown")
        model = validation_result.get("model", "unknown")
        alert_key = f"validation:{provider}:{model}"
        
        if self._is_in_cooldown(alert_key):
            return False
        
        alert_data = {
            "type": "pricing_validation",
            "severity": severity,
            "provider": provider,
            "model": model,
            "validation_result": validation_result,
            "message": self._format_validation_message(validation_result)
        }
        
        success = await self._send_alert(alert_data)
        
        if success:
            self._update_alert_tracking(alert_key)
        
        return success
    
    async def send_api_error_alert(
        self,
        provider: str,
        error_message: str,
        severity: str = "high"
    ) -> bool:
        """Send alert for pricing API errors."""
        if not self.config.alerts_enabled:
            return False
        
        alert_key = f"api_error:{provider}"
        if self._is_in_cooldown(alert_key):
            return False
        
        alert_data = {
            "type": "pricing_api_error",
            "severity": severity,
            "provider": provider,
            "error_message": error_message,
            "message": f"Pricing API error for {provider}: {error_message}"
        }
        
        success = await self._send_alert(alert_data)
        
        if success:
            self._update_alert_tracking(alert_key)
        
        return success
    
    def _is_in_cooldown(self, alert_key: str) -> bool:
        """Check if alert is in cooldown period."""
        import time
        
        last_alert_time = self._last_alert_times.get(alert_key, 0)
        return (time.time() - last_alert_time) < self._alert_cooldown
    
    def _update_alert_tracking(self, alert_key: str) -> None:
        """Update alert tracking."""
        import time
        
        self._last_alert_times[alert_key] = time.time()
        self._alert_count += 1
    
    def _format_pricing_change_message(
        self,
        provider: str,
        model: str,
        change_data: Dict[str, Any],
        severity: str
    ) -> str:
        """Format pricing change alert message."""
        change_percent = change_data.get("change_percent", 0)
        pricing_type = change_data.get("type", "unknown")
        previous_price = change_data.get("previous_price", 0)
        current_price = change_data.get("current_price", 0)
        
        direction = "increased" if change_percent > 0 else "decreased"
        
        return (
            f"🚨 {severity.upper()} PRICING ALERT\n"
            f"Provider: {provider}\n"
            f"Model: {model}\n"
            f"Token Type: {pricing_type}\n"
            f"Price {direction} by {abs(change_percent):.1f}%\n"
            f"Previous: ${previous_price:.6f} per 1K tokens\n"
            f"Current: ${current_price:.6f} per 1K tokens"
        )
    
    def _format_staleness_message(self, stale_items: List[Dict[str, Any]]) -> str:
        """Format staleness alert message."""
        message = f"⚠️ STALE PRICING DATA DETECTED\n"
        message += f"Found {len(stale_items)} stale pricing entries:\n\n"
        
        for item in stale_items[:5]:  # Show first 5 items
            provider = item.get("provider", "unknown")
            model = item.get("model", "unknown")
            age_hours = item.get("age_hours", 0)
            message += f"• {provider}:{model} - {age_hours:.1f} hours old\n"
        
        if len(stale_items) > 5:
            message += f"... and {len(stale_items) - 5} more"
        
        return message
    
    def _format_validation_message(self, validation_result: Dict[str, Any]) -> str:
        """Format validation alert message."""
        provider = validation_result.get("provider", "unknown")
        model = validation_result.get("model", "unknown")
        variance_percent = validation_result.get("variance_percent", 0)
        expected_cost = validation_result.get("expected_cost", 0)
        actual_cost = validation_result.get("actual_cost", 0)
        
        return (
            f"💰 PRICING VALIDATION ALERT\n"
            f"Provider: {provider}\n"
            f"Model: {model}\n"
            f"Expected Cost: ${expected_cost:.6f}\n"
            f"Actual Cost: ${actual_cost:.6f}\n"
            f"Variance: {variance_percent:.1f}%"
        )
    
    async def _send_alert(self, alert_data: Dict[str, Any]) -> bool:
        """Send alert through configured channels."""
        success = False
        
        for channel in self.config.alert_channels or ["webhook"]:
            try:
                if channel == "webhook" and self.config.alert_webhook_url:
                    success |= await self._send_webhook_alert(alert_data)
                elif channel == "email" and self.config.alert_email_recipients:
                    success |= await self._send_email_alert(alert_data)
                elif channel == "slack":
                    success |= await self._send_slack_alert(alert_data)
                else:
                    logger.warning(f"Unsupported alert channel: {channel}")
            
            except Exception as e:
                logger.error(f"Failed to send alert via {channel}: {e}")
        
        return success
    
    async def _send_webhook_alert(self, alert_data: Dict[str, Any]) -> bool:
        """Send alert via webhook."""
        if not self.config.alert_webhook_url:
            return False
        
        try:
            payload = {
                "alert": alert_data,
                "service": "atp-pricing-monitor",
                "timestamp": alert_data.get("timestamp", time.time())
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.config.alert_webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    response.raise_for_status()
                    logger.info(f"Webhook alert sent successfully: {alert_data['type']}")
                    return True
        
        except Exception as e:
            logger.error(f"Failed to send webhook alert: {e}")
            return False
    
    async def _send_email_alert(self, alert_data: Dict[str, Any]) -> bool:
        """Send alert via email."""
        # Email implementation would require SMTP configuration
        # For now, just log the alert
        logger.info(f"EMAIL ALERT: {alert_data['message']}")
        return True
    
    async def _send_slack_alert(self, alert_data: Dict[str, Any]) -> bool:
        """Send alert via Slack."""
        # Slack implementation would require Slack webhook URL
        # For now, just log the alert
        logger.info(f"SLACK ALERT: {alert_data['message']}")
        return True
    
    def get_alert_statistics(self) -> Dict[str, Any]:
        """Get alert statistics."""
        import time
        
        return {
            "alerts_enabled": self.config.alerts_enabled,
            "total_alerts_sent": self._alert_count,
            "alert_channels": self.config.alert_channels,
            "alert_cooldown_seconds": self._alert_cooldown,
            "recent_alerts": {
                key: time.time() - timestamp
                for key, timestamp in self._last_alert_times.items()
                if time.time() - timestamp < 3600  # Last hour
            }
        }