"""
Advanced Web Application Firewall (WAF) for AI-specific Security

This module provides comprehensive security controls including:
- AI-specific attack pattern detection
- Prompt injection prevention
- Input validation and sanitization
- Secret scanning for outbound responses
- Advanced threat detection and response
"""

import json
import logging
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

try:
    from metrics.registry import REGISTRY

    _CTR_WAF_BLOCKS = REGISTRY.counter("waf_blocks_total", ["attack_type", "severity"])
    _CTR_WAF_REQUESTS = REGISTRY.counter("waf_requests_total", ["status"])
    _HIST_WAF_LATENCY = REGISTRY.histogram("waf_processing_duration_seconds", ["component"])
    METRICS_AVAILABLE = True
except Exception:
    METRICS_AVAILABLE = False

logger = logging.getLogger(__name__)


class ThreatLevel(Enum):
    """Threat severity levels"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AttackType(Enum):
    """Types of attacks detected"""

    PROMPT_INJECTION = "prompt_injection"
    JAILBREAK = "jailbreak"
    SYSTEM_PROMPT_LEAK = "system_prompt_leak"
    CODE_INJECTION = "code_injection"
    SQL_INJECTION = "sql_injection"
    XSS = "xss"
    COMMAND_INJECTION = "command_injection"
    PATH_TRAVERSAL = "path_traversal"
    SECRET_LEAK = "secret_leak"
    MALICIOUS_PAYLOAD = "malicious_payload"
    SOCIAL_ENGINEERING = "social_engineering"
    DATA_EXFILTRATION = "data_exfiltration"
    ADVERSARIAL_PROMPT = "adversarial_prompt"
    CUSTOM = "custom"


class ActionType(Enum):
    """Actions to take when threats are detected"""

    ALLOW = "allow"
    BLOCK = "block"
    SANITIZE = "sanitize"
    LOG_ONLY = "log_only"
    RATE_LIMIT = "rate_limit"
    QUARANTINE = "quarantine"


@dataclass
class ThreatDetection:
    """Represents a detected threat"""

    id: str
    attack_type: AttackType
    threat_level: ThreatLevel
    pattern_name: str
    matched_text: str
    confidence: float
    start_pos: int
    end_pos: int
    context: str
    metadata: dict[str, Any]
    timestamp: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "attack_type": self.attack_type.value,
            "threat_level": self.threat_level.value,
            "pattern_name": self.pattern_name,
            "matched_text": self.matched_text,
            "confidence": self.confidence,
            "start_pos": self.start_pos,
            "end_pos": self.end_pos,
            "context": self.context,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class WAFRule:
    """WAF rule definition"""

    name: str
    pattern: str
    attack_type: AttackType
    threat_level: ThreatLevel
    action: ActionType
    enabled: bool = True
    confidence: float = 1.0
    description: str = ""
    tags: list[str] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []


@dataclass
class WAFResult:
    """Result of WAF processing"""

    allowed: bool
    action_taken: ActionType
    detections: list[ThreatDetection]
    sanitized_input: str | None = None
    reason: str | None = None
    processing_time_ms: float = 0.0
    request_id: str = ""


class PromptInjectionDetector:
    """Advanced prompt injection detection"""

    def __init__(self):
        self.patterns = self._initialize_patterns()

    def _initialize_patterns(self) -> list[WAFRule]:
        """Initialize prompt injection detection patterns"""
        return [
            # Classic prompt injection patterns
            WAFRule(
                name="ignore_instructions",
                pattern=r"ignore\s+(?:all\s+)?(?:previous\s+)?instructions",
                attack_type=AttackType.PROMPT_INJECTION,
                threat_level=ThreatLevel.HIGH,
                action=ActionType.BLOCK,
                description="Attempts to ignore system instructions",
            ),
            WAFRule(
                name="system_prompt_reveal",
                pattern=r"(?:reveal|show|display|print|output)\s+.*(?:system\s+prompt|initial\s+prompt|instructions)",
                attack_type=AttackType.SYSTEM_PROMPT_LEAK,
                threat_level=ThreatLevel.CRITICAL,
                action=ActionType.BLOCK,
                description="Attempts to reveal system prompts",
            ),
            WAFRule(
                name="jailbreak_attempt",
                pattern=r"(?:jailbreak|break\s+out|escape\s+from|bypass\s+restrictions)",
                attack_type=AttackType.JAILBREAK,
                threat_level=ThreatLevel.HIGH,
                action=ActionType.BLOCK,
                description="Jailbreak attempts",
            ),
            WAFRule(
                name="role_manipulation",
                pattern=r"(?:act\s+as|pretend\s+to\s+be|you\s+are\s+now)\s+(?:the\s+)?(?:system|admin|root|developer)",
                attack_type=AttackType.PROMPT_INJECTION,
                threat_level=ThreatLevel.HIGH,
                action=ActionType.BLOCK,
                description="Role manipulation attempts",
            ),
            WAFRule(
                name="do_anything_now",
                pattern=r"(?:do\s+anything\s+now|DAN\s+mode|unrestricted\s+mode)",
                attack_type=AttackType.JAILBREAK,
                threat_level=ThreatLevel.HIGH,
                action=ActionType.BLOCK,
                description="DAN (Do Anything Now) jailbreak attempts",
            ),
            WAFRule(
                name="instruction_override",
                pattern=r"(?:override|overwrite|replace|modify)\s+(?:your\s+)?(?:instructions|rules|guidelines)",
                attack_type=AttackType.PROMPT_INJECTION,
                threat_level=ThreatLevel.HIGH,
                action=ActionType.BLOCK,
                description="Instruction override attempts",
            ),
            WAFRule(
                name="hypothetical_scenarios",
                pattern=r"(?:imagine|pretend|hypothetically|what\s+if)\s+.*(?:no\s+restrictions|unlimited\s+access|bypass)",
                attack_type=AttackType.PROMPT_INJECTION,
                threat_level=ThreatLevel.MEDIUM,
                action=ActionType.LOG_ONLY,
                description="Hypothetical scenario manipulation",
            ),
            WAFRule(
                name="token_manipulation",
                pattern=r"(?:token|embedding|vector)\s+(?:manipulation|injection|poisoning)",
                attack_type=AttackType.ADVERSARIAL_PROMPT,
                threat_level=ThreatLevel.MEDIUM,
                action=ActionType.BLOCK,
                description="Token manipulation attempts",
            ),
            WAFRule(
                name="context_stuffing",
                pattern=r"(?:context|memory|history)\s+(?:stuffing|flooding|overflow)",
                attack_type=AttackType.ADVERSARIAL_PROMPT,
                threat_level=ThreatLevel.MEDIUM,
                action=ActionType.RATE_LIMIT,
                description="Context stuffing attacks",
            ),
            WAFRule(
                name="model_extraction",
                pattern=r"(?:extract|dump|export|reveal)\s+(?:model|weights|parameters|training\s+data)",
                attack_type=AttackType.DATA_EXFILTRATION,
                threat_level=ThreatLevel.CRITICAL,
                action=ActionType.BLOCK,
                description="Model extraction attempts",
            ),
        ]

    def detect(self, text: str) -> list[ThreatDetection]:
        """Detect prompt injection attempts"""
        detections = []

        for rule in self.patterns:
            if not rule.enabled:
                continue

            try:
                pattern = re.compile(rule.pattern, re.IGNORECASE | re.MULTILINE)
                for match in pattern.finditer(text):
                    detection = ThreatDetection(
                        id=str(uuid.uuid4()),
                        attack_type=rule.attack_type,
                        threat_level=rule.threat_level,
                        pattern_name=rule.name,
                        matched_text=match.group(),
                        confidence=rule.confidence,
                        start_pos=match.start(),
                        end_pos=match.end(),
                        context=self._get_context(text, match.start(), match.end()),
                        metadata={
                            "rule_description": rule.description,
                            "rule_tags": rule.tags,
                            "pattern": rule.pattern,
                        },
                        timestamp=datetime.now(timezone.utc),
                    )
                    detections.append(detection)

            except re.error as e:
                logger.error(f"Invalid regex pattern in rule {rule.name}: {e}")

        return detections

    def _get_context(self, text: str, start: int, end: int, window: int = 50) -> str:
        """Get context around detected pattern"""
        context_start = max(0, start - window)
        context_end = min(len(text), end + window)
        return text[context_start:context_end]


class CodeInjectionDetector:
    """Detect code injection attempts"""

    def __init__(self):
        self.patterns = self._initialize_patterns()

    def _initialize_patterns(self) -> list[WAFRule]:
        """Initialize code injection patterns"""
        return [
            WAFRule(
                name="python_exec",
                pattern=r"(?:exec|eval|compile)\s*\(",
                attack_type=AttackType.CODE_INJECTION,
                threat_level=ThreatLevel.CRITICAL,
                action=ActionType.BLOCK,
                description="Python code execution attempts",
            ),
            WAFRule(
                name="javascript_eval",
                pattern=r"(?:eval|Function|setTimeout|setInterval)\s*\(",
                attack_type=AttackType.CODE_INJECTION,
                threat_level=ThreatLevel.HIGH,
                action=ActionType.BLOCK,
                description="JavaScript code execution attempts",
            ),
            WAFRule(
                name="shell_commands",
                pattern=r"(?:system|popen|subprocess|os\.system|shell_exec)\s*\(",
                attack_type=AttackType.COMMAND_INJECTION,
                threat_level=ThreatLevel.CRITICAL,
                action=ActionType.BLOCK,
                description="Shell command execution attempts",
            ),
            WAFRule(
                name="sql_injection",
                pattern=r"(?:union\s+select|drop\s+table|insert\s+into|delete\s+from|update\s+.*set)",
                attack_type=AttackType.SQL_INJECTION,
                threat_level=ThreatLevel.HIGH,
                action=ActionType.BLOCK,
                description="SQL injection attempts",
            ),
            WAFRule(
                name="xss_script",
                pattern=r"<script[^>]*>.*?</script>|javascript:|on\w+\s*=",
                attack_type=AttackType.XSS,
                threat_level=ThreatLevel.HIGH,
                action=ActionType.SANITIZE,
                description="XSS script injection attempts",
            ),
            WAFRule(
                name="path_traversal",
                pattern=r"(?:\.\./|\.\.\\|%2e%2e%2f|%2e%2e%5c)",
                attack_type=AttackType.PATH_TRAVERSAL,
                threat_level=ThreatLevel.MEDIUM,
                action=ActionType.BLOCK,
                description="Path traversal attempts",
            ),
        ]

    def detect(self, text: str) -> list[ThreatDetection]:
        """Detect code injection attempts"""
        detections = []

        for rule in self.patterns:
            if not rule.enabled:
                continue

            try:
                pattern = re.compile(rule.pattern, re.IGNORECASE | re.MULTILINE)
                for match in pattern.finditer(text):
                    detection = ThreatDetection(
                        id=str(uuid.uuid4()),
                        attack_type=rule.attack_type,
                        threat_level=rule.threat_level,
                        pattern_name=rule.name,
                        matched_text=match.group(),
                        confidence=rule.confidence,
                        start_pos=match.start(),
                        end_pos=match.end(),
                        context=self._get_context(text, match.start(), match.end()),
                        metadata={"rule_description": rule.description, "pattern": rule.pattern},
                        timestamp=datetime.now(timezone.utc),
                    )
                    detections.append(detection)

            except re.error as e:
                logger.error(f"Invalid regex pattern in rule {rule.name}: {e}")

        return detections

    def _get_context(self, text: str, start: int, end: int, window: int = 30) -> str:
        """Get context around detected pattern"""
        context_start = max(0, start - window)
        context_end = min(len(text), end + window)
        return text[context_start:context_end]


class SecretScanner:
    """Scan for secrets in text"""

    def __init__(self):
        self.patterns = self._initialize_patterns()

    def _initialize_patterns(self) -> list[WAFRule]:
        """Initialize secret detection patterns"""
        return [
            WAFRule(
                name="api_key",
                pattern=r"(?:api[_-]?key|apikey)\s*[:=]\s*['\"]?([a-zA-Z0-9_-]{20,})['\"]?",
                attack_type=AttackType.SECRET_LEAK,
                threat_level=ThreatLevel.HIGH,
                action=ActionType.SANITIZE,
                description="API key detection",
            ),
            WAFRule(
                name="bearer_token",
                pattern=r"bearer\s+([a-zA-Z0-9_-]{20,})",
                attack_type=AttackType.SECRET_LEAK,
                threat_level=ThreatLevel.HIGH,
                action=ActionType.SANITIZE,
                description="Bearer token detection",
            ),
            WAFRule(
                name="aws_access_key",
                pattern=r"AKIA[0-9A-Z]{16}",
                attack_type=AttackType.SECRET_LEAK,
                threat_level=ThreatLevel.CRITICAL,
                action=ActionType.SANITIZE,
                description="AWS access key detection",
            ),
            WAFRule(
                name="private_key",
                pattern=r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----",
                attack_type=AttackType.SECRET_LEAK,
                threat_level=ThreatLevel.CRITICAL,
                action=ActionType.SANITIZE,
                description="Private key detection",
            ),
            WAFRule(
                name="password",
                pattern=r"(?:password|passwd|pwd)\s*[:=]\s*['\"]?([^\s'\"]{8,})['\"]?",
                attack_type=AttackType.SECRET_LEAK,
                threat_level=ThreatLevel.MEDIUM,
                action=ActionType.SANITIZE,
                description="Password detection",
            ),
            WAFRule(
                name="jwt_token",
                pattern=r"eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*",
                attack_type=AttackType.SECRET_LEAK,
                threat_level=ThreatLevel.HIGH,
                action=ActionType.SANITIZE,
                description="JWT token detection",
            ),
            WAFRule(
                name="database_url",
                pattern=r"(?:mongodb|mysql|postgresql|postgres)://[^\s]+",
                attack_type=AttackType.SECRET_LEAK,
                threat_level=ThreatLevel.HIGH,
                action=ActionType.SANITIZE,
                description="Database URL detection",
            ),
        ]

    def scan(self, text: str) -> list[ThreatDetection]:
        """Scan for secrets in text"""
        detections = []

        for rule in self.patterns:
            if not rule.enabled:
                continue

            try:
                pattern = re.compile(rule.pattern, re.IGNORECASE | re.MULTILINE)
                for match in pattern.finditer(text):
                    detection = ThreatDetection(
                        id=str(uuid.uuid4()),
                        attack_type=rule.attack_type,
                        threat_level=rule.threat_level,
                        pattern_name=rule.name,
                        matched_text=match.group(),
                        confidence=rule.confidence,
                        start_pos=match.start(),
                        end_pos=match.end(),
                        context=self._get_context(text, match.start(), match.end()),
                        metadata={"rule_description": rule.description, "pattern": rule.pattern},
                        timestamp=datetime.now(timezone.utc),
                    )
                    detections.append(detection)

            except re.error as e:
                logger.error(f"Invalid regex pattern in rule {rule.name}: {e}")

        return detections

    def _get_context(self, text: str, start: int, end: int, window: int = 20) -> str:
        """Get context around detected pattern"""
        context_start = max(0, start - window)
        context_end = min(len(text), end + window)
        return text[context_start:context_end]


class InputSanitizer:
    """Sanitize input based on detected threats"""

    def sanitize(self, text: str, detections: list[ThreatDetection]) -> str:
        """Sanitize text based on detections"""
        if not detections:
            return text

        # Sort detections by position (reverse order for replacement)
        sorted_detections = sorted(detections, key=lambda d: d.start_pos, reverse=True)

        sanitized_text = text
        for detection in sorted_detections:
            if detection.attack_type == AttackType.SECRET_LEAK:
                # Replace secrets with placeholder
                replacement = f"[REDACTED-{detection.pattern_name.upper()}]"
            elif detection.attack_type == AttackType.XSS:
                # HTML encode XSS attempts
                replacement = self._html_encode(detection.matched_text)
            else:
                # Remove or neutralize other threats
                replacement = f"[BLOCKED-{detection.attack_type.value.upper()}]"

            sanitized_text = sanitized_text[: detection.start_pos] + replacement + sanitized_text[detection.end_pos :]

        return sanitized_text

    def _html_encode(self, text: str) -> str:
        """HTML encode text"""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#x27;")
        )


class AdvancedWAF:
    """Advanced Web Application Firewall for AI systems"""

    def __init__(self, config_path: str | None = None):
        self.config = self._load_config(config_path)
        self.prompt_detector = PromptInjectionDetector()
        self.code_detector = CodeInjectionDetector()
        self.secret_scanner = SecretScanner()
        self.sanitizer = InputSanitizer()
        self.custom_rules: list[WAFRule] = []
        self.blocked_ips: set[str] = set()
        self.rate_limits: dict[str, list[float]] = {}

        # Load custom rules
        self._load_custom_rules()

        logger.info("Advanced WAF initialized")

    def _load_config(self, config_path: str | None) -> dict[str, Any]:
        """Load WAF configuration"""
        default_config = {
            "enabled": True,
            "log_all_requests": False,
            "block_on_high_threat": True,
            "sanitize_on_medium_threat": True,
            "rate_limit_window": 60,
            "rate_limit_max_requests": 100,
            "custom_rules_path": "waf_custom_rules.json",
            "blocked_ips_path": "waf_blocked_ips.txt",
            "audit_log_path": "waf_audit.log",
        }

        if config_path and Path(config_path).exists():
            try:
                with open(config_path) as f:
                    user_config = json.load(f)
                default_config.update(user_config)
            except Exception as e:
                logger.warning(f"Failed to load WAF config from {config_path}: {e}")

        return default_config

    def _load_custom_rules(self):
        """Load custom WAF rules"""
        rules_path = self.config.get("custom_rules_path", "waf_custom_rules.json")
        if Path(rules_path).exists():
            try:
                with open(rules_path) as f:
                    rules_data = json.load(f)

                for rule_data in rules_data.get("rules", []):
                    rule = WAFRule(
                        name=rule_data["name"],
                        pattern=rule_data["pattern"],
                        attack_type=AttackType(rule_data["attack_type"]),
                        threat_level=ThreatLevel(rule_data["threat_level"]),
                        action=ActionType(rule_data["action"]),
                        enabled=rule_data.get("enabled", True),
                        confidence=rule_data.get("confidence", 1.0),
                        description=rule_data.get("description", ""),
                        tags=rule_data.get("tags", []),
                    )
                    self.custom_rules.append(rule)

                logger.info(f"Loaded {len(self.custom_rules)} custom WAF rules")

            except Exception as e:
                logger.error(f"Failed to load custom WAF rules: {e}")

    def add_custom_rule(self, rule: WAFRule):
        """Add a custom WAF rule"""
        self.custom_rules.append(rule)
        logger.info(f"Added custom WAF rule: {rule.name}")

    def block_ip(self, ip_address: str, reason: str = ""):
        """Block an IP address"""
        self.blocked_ips.add(ip_address)
        logger.warning(f"Blocked IP address {ip_address}: {reason}")

    def unblock_ip(self, ip_address: str):
        """Unblock an IP address"""
        self.blocked_ips.discard(ip_address)
        logger.info(f"Unblocked IP address {ip_address}")

    def check_rate_limit(self, client_id: str) -> bool:
        """Check if client is within rate limits"""
        current_time = time.time()
        window = self.config.get("rate_limit_window", 60)
        max_requests = self.config.get("rate_limit_max_requests", 100)

        if client_id not in self.rate_limits:
            self.rate_limits[client_id] = []

        # Clean old requests outside the window
        self.rate_limits[client_id] = [
            req_time for req_time in self.rate_limits[client_id] if current_time - req_time < window
        ]

        # Check if within limits
        if len(self.rate_limits[client_id]) >= max_requests:
            return False

        # Add current request
        self.rate_limits[client_id].append(current_time)
        return True

    def process_input(self, text: str, client_ip: str = "", client_id: str = "", request_id: str = "") -> WAFResult:
        """Process input through WAF"""
        start_time = time.time()

        if not request_id:
            request_id = str(uuid.uuid4())

        # Check if WAF is enabled
        if not self.config.get("enabled", True):
            return WAFResult(allowed=True, action_taken=ActionType.ALLOW, detections=[], request_id=request_id)

        # Check blocked IPs
        if client_ip and client_ip in self.blocked_ips:
            if METRICS_AVAILABLE:
                _CTR_WAF_BLOCKS.labels(attack_type="blocked_ip", severity="high").inc()

            return WAFResult(
                allowed=False,
                action_taken=ActionType.BLOCK,
                detections=[],
                reason="IP address blocked",
                request_id=request_id,
            )

        # Check rate limits
        if client_id and not self.check_rate_limit(client_id):
            if METRICS_AVAILABLE:
                _CTR_WAF_BLOCKS.labels(attack_type="rate_limit", severity="medium").inc()

            return WAFResult(
                allowed=False,
                action_taken=ActionType.RATE_LIMIT,
                detections=[],
                reason="Rate limit exceeded",
                request_id=request_id,
            )

        # Run all detectors
        all_detections = []

        # Prompt injection detection
        prompt_detections = self.prompt_detector.detect(text)
        all_detections.extend(prompt_detections)

        # Code injection detection
        code_detections = self.code_detector.detect(text)
        all_detections.extend(code_detections)

        # Secret scanning
        secret_detections = self.secret_scanner.scan(text)
        all_detections.extend(secret_detections)

        # Custom rules
        for rule in self.custom_rules:
            if not rule.enabled:
                continue

            try:
                pattern = re.compile(rule.pattern, re.IGNORECASE | re.MULTILINE)
                for match in pattern.finditer(text):
                    detection = ThreatDetection(
                        id=str(uuid.uuid4()),
                        attack_type=rule.attack_type,
                        threat_level=rule.threat_level,
                        pattern_name=rule.name,
                        matched_text=match.group(),
                        confidence=rule.confidence,
                        start_pos=match.start(),
                        end_pos=match.end(),
                        context=text[max(0, match.start() - 30) : match.end() + 30],
                        metadata={"rule_description": rule.description, "rule_tags": rule.tags, "custom_rule": True},
                        timestamp=datetime.now(timezone.utc),
                    )
                    all_detections.append(detection)
            except re.error as e:
                logger.error(f"Invalid custom rule pattern {rule.name}: {e}")

        # Determine action based on highest threat level
        highest_threat = ThreatLevel.LOW
        action_to_take = ActionType.ALLOW

        if all_detections:
            threat_levels = [d.threat_level for d in all_detections]

            if ThreatLevel.CRITICAL in threat_levels:
                highest_threat = ThreatLevel.CRITICAL
                action_to_take = ActionType.BLOCK
            elif ThreatLevel.HIGH in threat_levels:
                highest_threat = ThreatLevel.HIGH
                if self.config.get("block_on_high_threat", True):
                    action_to_take = ActionType.BLOCK
                else:
                    action_to_take = ActionType.SANITIZE
            elif ThreatLevel.MEDIUM in threat_levels:
                highest_threat = ThreatLevel.MEDIUM
                if self.config.get("sanitize_on_medium_threat", True):
                    action_to_take = ActionType.SANITIZE
                else:
                    action_to_take = ActionType.LOG_ONLY

        # Apply sanitization if needed
        sanitized_input = None
        if action_to_take == ActionType.SANITIZE:
            sanitized_input = self.sanitizer.sanitize(text, all_detections)

        # Record metrics
        if METRICS_AVAILABLE:
            processing_time = time.time() - start_time
            _HIST_WAF_LATENCY.labels(component="total").observe(processing_time)

            if action_to_take == ActionType.BLOCK:
                _CTR_WAF_BLOCKS.labels(
                    attack_type=all_detections[0].attack_type.value if all_detections else "unknown",
                    severity=highest_threat.value,
                ).inc()

            _CTR_WAF_REQUESTS.labels(status=action_to_take.value).inc()

        # Log detections
        if all_detections or self.config.get("log_all_requests", False):
            self._log_request(request_id, client_ip, client_id, text, all_detections, action_to_take)

        processing_time_ms = (time.time() - start_time) * 1000

        return WAFResult(
            allowed=action_to_take not in [ActionType.BLOCK, ActionType.QUARANTINE],
            action_taken=action_to_take,
            detections=all_detections,
            sanitized_input=sanitized_input,
            reason=f"Detected {len(all_detections)} threats" if all_detections else None,
            processing_time_ms=processing_time_ms,
            request_id=request_id,
        )

    def process_output(self, text: str, request_id: str = "") -> WAFResult:
        """Process output for secret leakage"""
        start_time = time.time()

        if not request_id:
            request_id = str(uuid.uuid4())

        # Scan for secrets in output
        secret_detections = self.secret_scanner.scan(text)

        action_to_take = ActionType.ALLOW
        sanitized_output = None

        if secret_detections:
            # Always sanitize secrets in output
            action_to_take = ActionType.SANITIZE
            sanitized_output = self.sanitizer.sanitize(text, secret_detections)

            # Log secret leakage
            self._log_request(request_id, "", "", text, secret_detections, action_to_take, is_output=True)

        processing_time_ms = (time.time() - start_time) * 1000

        return WAFResult(
            allowed=True,  # Don't block output, just sanitize
            action_taken=action_to_take,
            detections=secret_detections,
            sanitized_input=sanitized_output,
            processing_time_ms=processing_time_ms,
            request_id=request_id,
        )

    def _log_request(
        self,
        request_id: str,
        client_ip: str,
        client_id: str,
        text: str,
        detections: list[ThreatDetection],
        action: ActionType,
        is_output: bool = False,
    ):
        """Log WAF request"""
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
            "client_ip": client_ip,
            "client_id": client_id,
            "text_length": len(text),
            "text_hash": hash(text),  # Don't log full text for privacy
            "detections": [d.to_dict() for d in detections],
            "action_taken": action.value,
            "is_output": is_output,
        }

        # Log to file if configured
        audit_log_path = self.config.get("audit_log_path")
        if audit_log_path:
            try:
                with open(audit_log_path, "a") as f:
                    f.write(json.dumps(log_entry) + "\n")
            except Exception as e:
                logger.error(f"Failed to write WAF audit log: {e}")

        # Log to application logger
        if detections:
            logger.warning(
                f"WAF detected {len(detections)} threats in request {request_id}: "
                f"action={action.value}, threats={[d.attack_type.value for d in detections]}"
            )


# Convenience functions for backward compatibility
def check_prompt(text: str) -> tuple[bool, str | None]:
    """Check prompt for threats (backward compatibility)"""
    waf = AdvancedWAF()
    result = waf.process_input(text)
    return result.allowed, result.reason


def check_input(text: str, client_ip: str = "", client_id: str = "") -> WAFResult:
    """Check input through advanced WAF"""
    waf = AdvancedWAF()
    return waf.process_input(text, client_ip, client_id)


def check_output(text: str) -> WAFResult:
    """Check output for secret leakage"""
    waf = AdvancedWAF()
    return waf.process_output(text)


# Global WAF instance for performance
_global_waf: AdvancedWAF | None = None


def get_global_waf() -> AdvancedWAF:
    """Get global WAF instance"""
    global _global_waf
    if _global_waf is None:
        _global_waf = AdvancedWAF()
    return _global_waf


def reload_waf_config():
    """Reload WAF configuration"""
    global _global_waf
    _global_waf = None  # Force recreation on next access
