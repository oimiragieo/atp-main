"""GAP-213: Carbon intensity tracking and routing influence.

This module provides carbon intensity data integration and routing influence
based on regional carbon emissions data.
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta

import aiohttp

from metrics.registry import CARBON_API_ERRORS_TOTAL, CARBON_API_REQUESTS_TOTAL

logger = logging.getLogger(__name__)


@dataclass
class CarbonIntensityData:
    """Carbon intensity data for a region."""

    region: str
    intensity_gco2_per_kwh: float  # grams CO2 per kWh
    timestamp: datetime
    source: str
    confidence: float  # 0-1


class CarbonIntensityTracker:
    """Tracks carbon intensity by region and provides routing influence."""

    def __init__(self, api_key: str | None = None, cache_ttl_seconds: int = 3600):
        """Initialize carbon intensity tracker.

        Args:
            api_key: API key for carbon intensity service (if required)
            cache_ttl_seconds: How long to cache carbon data
        """
        self.api_key = api_key or "demo"  # Use demo key if none provided
        self.cache_ttl = cache_ttl_seconds
        self._cache: dict[str, CarbonIntensityData] = {}
        self._session: aiohttp.ClientSession | None = None

        # Demo data for regions (fallback when API unavailable)
        self._demo_data = {
            "us-west": 200.0,  # California average
            "us-east": 250.0,  # East coast average
            "eu-west": 150.0,  # Germany/Netherlands
            "eu-central": 180.0,  # Central Europe
            "asia-east": 400.0,  # China average
            "asia-south": 500.0,  # India average
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _fetch_carbon_intensity(self, region: str) -> CarbonIntensityData | None:
        """Fetch carbon intensity data from external API.

        Uses Electricity Maps API or similar service.
        Falls back to demo data if API unavailable.
        """
        CARBON_API_REQUESTS_TOTAL.inc()

        try:
            session = await self._get_session()

            # Try Electricity Maps API (requires API key)
            if self.api_key != "demo":
                url = f"https://api.electricitymaps.com/v3/carbon-intensity/latest?zone={region}"
                headers = {"auth-token": self.api_key}

                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        return CarbonIntensityData(
                            region=region,
                            intensity_gco2_per_kwh=data.get("carbonIntensity", 0),
                            timestamp=datetime.now(),
                            source="electricitymaps",
                            confidence=0.9,
                        )

            # Fallback to demo data
            if region in self._demo_data:
                return CarbonIntensityData(
                    region=region,
                    intensity_gco2_per_kwh=self._demo_data[region],
                    timestamp=datetime.now(),
                    source="demo",
                    confidence=0.7,
                )

        except Exception as e:
            CARBON_API_ERRORS_TOTAL.inc()
            logger.warning(f"Failed to fetch carbon data for {region}: {e}")

        return None

    async def get_carbon_intensity(self, region: str) -> CarbonIntensityData | None:
        """Get carbon intensity for a region, with caching."""
        # Check cache first
        if region in self._cache:
            cached = self._cache[region]
            if datetime.now() - cached.timestamp < timedelta(seconds=self.cache_ttl):
                return cached

        # Fetch fresh data
        data = await self._fetch_carbon_intensity(region)
        if data:
            self._cache[region] = data

        return data

    def calculate_routing_weight(
        self, region: str, base_weight: float = 1.0, carbon_penalty_factor: float = 0.001
    ) -> float:
        """Calculate routing weight adjusted for carbon intensity.

        Args:
            region: Region code
            base_weight: Base routing weight (cost, latency, etc.)
            carbon_penalty_factor: How much to penalize high carbon regions

        Returns:
            Adjusted weight (higher = less preferred)
        """
        # Get cached data (synchronous for routing decisions)
        data = self._cache.get(region)
        if not data:
            # Use demo data as fallback for routing decisions
            intensity = self._demo_data.get(region, 300.0)  # Global average fallback
        else:
            intensity = data.intensity_gco2_per_kwh

        # Calculate carbon penalty (higher intensity = higher penalty)
        carbon_penalty = intensity * carbon_penalty_factor

        # Adjust base weight by carbon penalty
        adjusted_weight = base_weight * (1.0 + carbon_penalty)

        logger.debug(
            f"Region {region}: intensity={intensity}g/kWh, penalty={carbon_penalty:.4f}, weight={adjusted_weight:.4f}"
        )

        return adjusted_weight

    def get_carbon_aware_regions(self, regions: list[str]) -> list[tuple[str, float]]:
        """Get regions sorted by carbon efficiency (lowest carbon first)."""
        region_scores = []
        for region in regions:
            data = self._cache.get(region)
            intensity = data.intensity_gco2_per_kwh if data else self._demo_data.get(region, 300.0)
            region_scores.append((region, intensity))

        # Sort by carbon intensity (ascending = more efficient)
        return sorted(region_scores, key=lambda x: x[1])

    async def close(self):
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()


# Global instance for use across the application
_carbon_tracker: CarbonIntensityTracker | None = None


def get_carbon_tracker() -> CarbonIntensityTracker:
    """Get global carbon intensity tracker instance."""
    global _carbon_tracker
    if _carbon_tracker is None:
        api_key = os.environ.get("CARBON_API_KEY", "demo")  # Load from environment or use demo
        _carbon_tracker = CarbonIntensityTracker(api_key=api_key)
    return _carbon_tracker
