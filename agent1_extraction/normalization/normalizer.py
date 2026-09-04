from typing import Optional
from geopy.geocoders import Nominatim
from loguru import logger
from agent1_extraction.config import settings
from agent1_extraction.models.schemas import NormalizedGeo


class EntityNormalizer:
  """Normalizes location and temporal strings into standardized structured data."""

  def __init__(self):
    self.enabled = settings.GEO_NORMALIZATION_ENABLED
    if self.enabled:
      self.geolocator = Nominatim(user_agent="sih_agent1_forensics")

  def normalize_location(self, raw_geo: str) -> Optional[NormalizedGeo]:
    if not raw_geo or not self.enabled:
      return None

    try:
      # Append city context if missing to improve geocoding resolution
      query = (
          f"{raw_geo}, Mumbai, India"
          if "Mumbai" not in raw_geo
          else raw_geo
      )
      location = self.geolocator.geocode(query, timeout=3)
      if location:
        return NormalizedGeo(
            raw_location=raw_geo,
            formatted_address=location.address,
            latitude=location.latitude,
            longitude=location.longitude,
        )
    except Exception as e:
      logger.debug(f"Geocoding lookup bypassed for '{raw_geo}': {e}")

    return NormalizedGeo(
        raw_location=raw_geo,
        formatted_address=raw_geo,
        latitude=19.1176,  # Default fallback coordinates for Andheri/Goregaon West area
        longitude=72.8481,
    )