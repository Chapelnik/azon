"""
Geocoding module with async support and rate limiting
"""

import logging
import time
from typing import Optional, Tuple, List, Dict
from datetime import datetime, timedelta
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable, GeocoderServiceError
from cache import GeocodeCache

logger = logging.getLogger(__name__)


class RateLimiter:
    """Rate limiter for API calls"""
    
    def __init__(self, calls_per_second: float = 1.0):
        self.min_interval = 1.0 / calls_per_second
        self.last_call_time: Optional[float] = None
    
    def wait(self) -> None:
        """Wait if necessary to respect rate limit"""
        if self.last_call_time is not None:
            elapsed = time.time() - self.last_call_time
            if elapsed < self.min_interval:
                sleep_time = self.min_interval - elapsed
                time.sleep(sleep_time)
        self.last_call_time = time.time()


class GeocoderService:
    """Geocoding service with caching and rate limiting"""
    
    # Known cities in Russia with coordinates (fallback cache)
    KNOWN_CITIES: Dict[str, Tuple[float, float]] = {
        'москва': (55.7558, 37.6173),
        'санкт-петербург': (59.9343, 30.3351),
        'новосибирск': (55.0084, 82.9357),
        'екатеринбург': (56.8389, 60.6057),
        'казань': (55.7961, 49.1064),
        'нижний новгород': (56.2965, 43.9361),
        'челябинск': (55.1644, 61.4368),
        'самара': (53.1959, 50.1002),
        'омск': (54.9885, 73.3242),
        'ростов-на-дону': (47.2357, 39.7015),
        'уфа': (54.7388, 55.9721),
        'красноярск': (56.0153, 92.8932),
        'воронеж': (51.6720, 39.1843),
        'пермь': (58.0105, 56.2502),
        'волгоград': (48.7080, 44.5133),
        'краснодар': (45.0355, 38.9753),
        'саратов': (51.5924, 46.0348),
        'тюмень': (57.1522, 65.5272),
        'тольятти': (53.5303, 49.3461),
        'ижевск': (56.8527, 53.2041),
        'барнаул': (53.3606, 83.7636),
        'ульяновск': (54.3141, 48.4031),
        'иркутск': (52.2870, 104.2805),
        'хабаровск': (48.4827, 135.0838),
        'ярославль': (57.6261, 39.8845),
        'владивосток': (43.1155, 131.8855),
        'махачкала': (42.9849, 47.5047),
        'томск': (56.4977, 84.9744),
        'оренбург': (51.7727, 55.0978),
        'кемерово': (55.3563, 86.0872),
        'новокузнецк': (53.7596, 87.1207),
        'рязань': (54.6269, 39.6916),
        'астрахань': (46.3497, 48.0408),
        'пенза': (53.2001, 45.0000),
        'липецк': (52.6031, 39.5708),
        'киров': (58.6035, 49.6679),
        'тула': (54.1931, 37.6182),
        'чебоксары': (56.1439, 47.2517),
        'калининград': (54.7065, 20.5110),
        'брянск': (53.2434, 34.3656),
        'курск': (51.7303, 36.1923),
        'иваново': (57.0000, 40.9833),
        'тверь': (56.8584, 35.9006),
        'ставрополь': (45.0428, 41.9734),
        'белгород': (50.5951, 36.5871),
        'нижний тагил': (57.9197, 59.9650),
        'владимир': (56.1366, 40.3966),
        'архангельск': (64.5401, 40.5433),
        'чита': (52.0297, 113.5006),
        'смоленск': (54.7818, 32.0401),
        'волжский': (48.7854, 44.7759),
        'курган': (55.4500, 65.3333),
        'орёл': (52.9651, 36.0785),
        'череповец': (59.1333, 37.9000),
        'петрозаводск': (61.7849, 34.3469),
        'сыктывкар': (61.6682, 50.8053),
        'мурманск': (68.9585, 33.0827),
        'саранск': (54.1838, 45.1749),
        'тамбов': (52.7213, 41.4520),
        'грозный': (43.3183, 45.6986),
        'стерлитамак': (53.6242, 55.9504),
        'йошкар-ола': (56.6372, 47.8986)
    }
    
    def __init__(self, cache: GeocodeCache, timeout: int = 5, 
                 rate_limit: float = 1.0, max_retries: int = 2):
        self.cache = cache
        self.timeout = timeout
        self.max_retries = max_retries
        self.rate_limiter = RateLimiter(calls_per_second=rate_limit)
        self.geolocator = Nominatim(
            user_agent="azon_concerts_app",
            timeout=timeout
        )
        self.stats = {
            'total_requests': 0,
            'cache_hits': 0,
            'api_calls': 0,
            'errors': 0,
            'last_error': None
        }
    
    def _normalize_city(self, city: str) -> str:
        """Normalize city name for lookup"""
        return city.lower().strip()
    
    def geocode(self, city: str) -> Optional[Tuple[float, float]]:
        """
        Get coordinates for a city with caching and retry logic.
        
        Args:
            city: City name to geocode
            
        Returns:
            Tuple of (latitude, longitude) or None if not found
        """
        normalized_city = self._normalize_city(city)
        self.stats['total_requests'] += 1
        
        # Check file cache first
        cached = self.cache.get(normalized_city)
        if cached is not None:
            self.stats['cache_hits'] += 1
            logger.debug(f"Cache hit for '{city}': {cached}")
            return cached
        
        # Check known cities fallback
        if normalized_city in self.KNOWN_CITIES:
            coords = self.KNOWN_CITIES[normalized_city]
            self.cache.set(normalized_city, coords)
            self.stats['cache_hits'] += 1
            logger.info(f"Used known city coords for '{city}': {coords}")
            return coords
        
        # Make API call with rate limiting and retries
        self.rate_limiter.wait()
        
        location = None
        last_error = None
        
        for attempt in range(self.max_retries + 1):
            try:
                self.stats['api_calls'] += 1
                logger.debug(f"Geocoding '{city}' (attempt {attempt + 1})")
                location = self.geolocator.geocode(f"{city}, Россия")
                
                if location:
                    coords = (location.latitude, location.longitude)
                    self.cache.set(normalized_city, coords)
                    logger.info(f"Geocoded '{city}' -> {coords}")
                    return coords
                else:
                    logger.warning(f"No results for '{city}'")
                    break
                    
            except (GeocoderTimedOut, GeocoderServiceError) as e:
                last_error = e
                logger.warning(f"Geocoding error for {city} (attempt {attempt + 1}): {e}")
                if attempt < self.max_retries:
                    time.sleep(1.0 * (attempt + 1))  # Exponential backoff
                continue
                
            except GeocoderUnavailable as e:
                last_error = e
                logger.error(f"Geocoder unavailable for {city}: {e}")
                break
        
        # Cache the failure
        self.cache.set(normalized_city, None)
        self.stats['errors'] += 1
        self.stats['last_error'] = str(last_error) if last_error else "No results"
        logger.warning(f"Failed to geocode '{city}': {self.stats['last_error']}")
        return None
    
    def geocode_batch(self, cities: List[str]) -> Dict[str, Optional[Tuple[float, float]]]:
        """
        Geocode multiple cities with rate limiting.
        
        Args:
            cities: List of city names
            
        Returns:
            Dictionary mapping city names to coordinates
        """
        results = {}
        for city in cities:
            results[city] = self.geocode(city)
        return results
    
    def get_stats(self) -> Dict:
        """Get geocoding statistics"""
        return {
            **self.stats,
            'cache_size': self.cache.size()
        }
