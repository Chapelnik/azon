"""
Cache module with file-based and Redis support
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class FileCache:
    """File-based cache with TTL support"""
    
    def __init__(self, cache_file: str, ttl_hours: int = 24):
        self.cache_file = Path(cache_file)
        self.ttl = timedelta(hours=ttl_hours)
        self.data = self._load()
    
    def _load(self) -> List[Dict[str, Any]]:
        """Load cache from file"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    cached_time = datetime.fromisoformat(data.get('timestamp', '1970-01-01'))
                    if datetime.now() - cached_time < self.ttl:
                        logger.info(f"Loaded cache from {self.cache_file}")
                        return data.get('content', [])
                    else:
                        logger.info("Cache expired")
                        return []
            except (json.JSONDecodeError, Exception) as e:
                logger.error(f"Error loading cache: {e}")
                return []
        return []
    
    def save(self, content: List[Dict[str, Any]]) -> bool:
        """Save content to cache file"""
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            data = {'timestamp': datetime.now().isoformat(), 'content': content}
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved cache to {self.cache_file}")
            return True
        except Exception as e:
            logger.error(f"Error saving cache: {e}")
            return False
    
    def get(self) -> List[Dict[str, Any]]:
        """Get cached content"""
        return self.data
    
    def is_valid(self) -> bool:
        """Check if cache is still valid"""
        if not self.cache_file.exists():
            return False
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                cached_time = datetime.fromisoformat(data.get('timestamp', '1970-01-01'))
                return datetime.now() - cached_time < self.ttl
        except Exception:
            return False
    
    def clear(self) -> bool:
        """Clear the cache"""
        try:
            if self.cache_file.exists():
                self.cache_file.unlink()
            self.data = []
            logger.info(f"Cleared cache: {self.cache_file}")
            return True
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            return False


try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.info("Redis not available, install with: pip install redis")


class RedisCache:
    """Redis-based cache for production use"""
    
    def __init__(self, host: str = 'localhost', port: int = 6379, 
                 db: int = 0, key_prefix: str = 'concerts:', ttl_seconds: int = 86400):
        if not REDIS_AVAILABLE:
            raise ImportError("Redis library not installed. Install with: pip install redis")
        
        self.redis_client = redis.Redis(host=host, port=port, db=db, decode_responses=True)
        self.key_prefix = key_prefix
        self.ttl_seconds = ttl_seconds
        self._test_connection()
    
    def _test_connection(self) -> None:
        """Test Redis connection"""
        try:
            self.redis_client.ping()
            logger.info("Connected to Redis successfully")
        except redis.ConnectionError as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    def set(self, key: str, value: Any) -> bool:
        """Set a value in cache"""
        try:
            full_key = f"{self.key_prefix}{key}"
            self.redis_client.setex(full_key, self.ttl_seconds, json.dumps(value))
            logger.debug(f"Set cache key: {full_key}")
            return True
        except Exception as e:
            logger.error(f"Error setting Redis cache: {e}")
            return False
    
    def get(self, key: str) -> Optional[Any]:
        """Get a value from cache"""
        try:
            full_key = f"{self.key_prefix}{key}"
            data = self.redis_client.get(full_key)
            if data:
                logger.debug(f"Cache hit for key: {full_key}")
                return json.loads(data)
            logger.debug(f"Cache miss for key: {full_key}")
            return None
        except Exception as e:
            logger.error(f"Error getting Redis cache: {e}")
            return None
    
    def delete(self, key: str) -> bool:
        """Delete a key from cache"""
        try:
            full_key = f"{self.key_prefix}{key}"
            self.redis_client.delete(full_key)
            logger.debug(f"Deleted cache key: {full_key}")
            return True
        except Exception as e:
            logger.error(f"Error deleting Redis cache: {e}")
            return False
    
    def clear(self) -> bool:
        """Clear all keys with prefix"""
        try:
            keys = self.redis_client.keys(f"{self.key_prefix}*")
            if keys:
                self.redis_client.delete(*keys)
            logger.info(f"Cleared {len(keys)} Redis cache keys")
            return True
        except Exception as e:
            logger.error(f"Error clearing Redis cache: {e}")
            return False


class GeocodeCache:
    """Specialized cache for geocoding results"""
    
    def __init__(self, cache_file: str = '.cache/geocode_cache.json'):
        self.cache_file = Path(cache_file)
        self.data: Dict[str, Optional[tuple]] = {}
        self._load()
    
    def _load(self) -> None:
        """Load geocode cache from file"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    raw_data = json.load(f)
                    # Convert list coords back to tuples
                    self.data = {
                        k: tuple(v) if isinstance(v, list) else v 
                        for k, v in raw_data.items()
                    }
                logger.info(f"Loaded geocode cache with {len(self.data)} entries")
            except Exception as e:
                logger.error(f"Error loading geocode cache: {e}")
                self.data = {}
    
    def get(self, city: str) -> Optional[tuple]:
        """Get cached coordinates for a city"""
        return self.data.get(city)
    
    def set(self, city: str, coords: Optional[tuple]) -> None:
        """Cache coordinates for a city"""
        self.data[city] = coords
        self._save()
    
    def _save(self) -> None:
        """Save geocode cache to file"""
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            # Convert tuples to lists for JSON serialization
            serializable_data = {
                k: list(v) if v is not None else None 
                for k, v in self.data.items()
            }
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(serializable_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving geocode cache: {e}")
    
    def size(self) -> int:
        """Return number of cached entries"""
        return len(self.data)
