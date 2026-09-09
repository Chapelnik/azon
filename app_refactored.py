"""
Flask application for concert map display
Refactored with modular architecture
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

from flask import Flask, render_template, jsonify, request
from dotenv import load_dotenv

# Import custom modules
from scraper import ConcertScraper
from cache import FileCache, GeocodeCache, RedisCache
from geocoder import GeocoderService
from logging_config import setup_logging, health_checker, get_logger

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__, 
            template_folder='templates',
            static_folder='static')


def load_config() -> Dict[str, Any]:
    """Load configuration from file and environment variables"""
    config_path = Path(__file__).parent / 'config.json'
    config = {}
    
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    
    # Override with environment variables (more secure)
    if os.getenv('CARTO_API_KEY'):
        config.setdefault('carto', {})['api_key'] = os.getenv('CARTO_API_KEY')
    if os.getenv('CARTO_USERNAME'):
        config.setdefault('carto', {})['username'] = os.getenv('CARTO_USERNAME')
    if os.getenv('REDIS_HOST'):
        config.setdefault('redis', {})['host'] = os.getenv('REDIS_HOST')
    if os.getenv('SECRET_KEY'):
        app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
    
    return config


# Load configuration
CONFIG = load_config()

# Setup logging
logger = setup_logging(CONFIG.get('logging', {}))


class ConcertService:
    """Service for managing concert data"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.scraper = ConcertScraper(
            timeout=config.get('scraper', {}).get('timeout', 10),
            max_retries=config.get('scraper', {}).get('max_retries', 3)
        )
        
        # Initialize cache
        cache_config = config.get('cache', {})
        if cache_config.get('enabled', True):
            # Try Redis first, fallback to file cache
            redis_config = config.get('redis', {})
            if redis_config.get('enabled', False):
                try:
                    self.concerts_cache = RedisCache(
                        host=redis_config.get('host', 'localhost'),
                        port=redis_config.get('port', 6379),
                        ttl_seconds=cache_config.get('ttl_hours', 24) * 3600
                    )
                    logger.info("Using Redis cache")
                except Exception as e:
                    logger.warning(f"Redis not available, using file cache: {e}")
                    self._init_file_cache(cache_config)
            else:
                self._init_file_cache(cache_config)
        else:
            self.concerts_cache = None
        
        # Initialize geocoder
        self.geocode_cache = GeocodeCache(
            config.get('geocode_cache', {}).get('file_path', '.cache/geocode_cache.json')
        )
        geocoder_config = config.get('geocoder', {})
        self.geocoder = GeocoderService(
            cache=self.geocode_cache,
            timeout=geocoder_config.get('timeout', 5),
            rate_limit=geocoder_config.get('rate_limit', 1.0),
            max_retries=geocoder_config.get('max_retries', 2)
        )
        
        # Statistics
        self.stats = {
            'total_requests': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'parse_errors': 0,
            'geocode_errors': 0,
            'last_updated': None
        }
    
    def _init_file_cache(self, cache_config: Dict[str, Any]) -> None:
        """Initialize file-based cache"""
        self.concerts_cache = FileCache(
            cache_config.get('file_path', '.cache/concerts_cache.json'),
            ttl_hours=cache_config.get('ttl_hours', 24)
        )
        logger.info("Using file cache")
    
    def get_concerts(self, force_refresh: bool = False) -> List[Dict[str, str]]:
        """Get concerts with caching"""
        self.stats['total_requests'] += 1
        
        # Check cache
        if self.concerts_cache and not force_refresh:
            if isinstance(self.concerts_cache, FileCache) and self.concerts_cache.is_valid():
                self.stats['cache_hits'] += 1
                logger.info("Using cached concerts data")
                return self.concerts_cache.get()
            elif isinstance(self.concerts_cache, RedisCache):
                cached = self.concerts_cache.get('concerts')
                if cached:
                    self.stats['cache_hits'] += 1
                    logger.info("Using cached concerts data (Redis)")
                    return cached
        
        self.stats['cache_misses'] += 1
        logger.info("Fetching fresh concerts data")
        
        # Fetch fresh data
        try:
            concerts = self.scraper.get_concerts()
            
            # Save to cache
            if self.concerts_cache:
                if isinstance(self.concerts_cache, FileCache):
                    self.concerts_cache.save(concerts)
                elif isinstance(self.concerts_cache, RedisCache):
                    self.concerts_cache.set('concerts', concerts)
            
            self.stats['last_updated'] = datetime.now().isoformat()
            logger.info(f"Parsed {len(concerts)} concerts")
            return concerts
            
        except Exception as e:
            logger.error(f"Error fetching concerts: {e}")
            self.stats['parse_errors'] += 1
            return []
    
    def get_concerts_with_coords(self) -> List[Dict[str, Any]]:
        """Get concerts with geocoded coordinates"""
        concerts = self.get_concerts()
        result = []
        cities_processed = set()
        
        for concert in concerts:
            city = concert['city']
            if city in cities_processed:
                continue
            
            cities_processed.add(city)
            coords = self.geocoder.geocode(city)
            
            if coords:
                result.append({
                    **concert,
                    'lat': coords[0],
                    'lng': coords[1]
                })
            else:
                self.stats['geocode_errors'] += 1
                logger.warning(f"Could not geocode city: {city}")
        
        logger.info(f"API returned {len(result)} concerts with coordinates")
        return result
    
    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics"""
        return {
            **self.stats,
            'cache_enabled': self.concerts_cache is not None,
            'geocode_cache_size': self.geocode_cache.size(),
            'geocoder_stats': self.geocoder.get_stats()
        }
    
    def refresh_cache(self) -> bool:
        """Force refresh the cache"""
        try:
            concerts = self.scraper.get_concerts()
            if self.concerts_cache:
                if isinstance(self.concerts_cache, FileCache):
                    self.concerts_cache.save(concerts)
                elif isinstance(self.concerts_cache, RedisCache):
                    self.concerts_cache.set('concerts', concerts)
            self.stats['last_updated'] = datetime.now().isoformat()
            logger.info("Cache refreshed successfully")
            return True
        except Exception as e:
            logger.error(f"Error refreshing cache: {e}")
            return False


# Initialize service
concert_service = ConcertService(CONFIG)


@app.route('/')
def index() -> str:
    """Render main page"""
    carto_config = CONFIG.get('carto', {})
    api_key = carto_config.get('api_key', '')
    username = carto_config.get('username', '')
    return render_template('index.html', api_key=api_key, username=username)


@app.route('/api/concerts')
def get_concerts_api() -> jsonify:
    """API endpoint for concerts with coordinates"""
    concerts = concert_service.get_concerts_with_coords()
    return jsonify(concerts)


@app.route('/api/stats')
def get_stats() -> jsonify:
    """API endpoint for statistics"""
    return jsonify(concert_service.get_stats())


@app.route('/api/health')
def health_check() -> jsonify:
    """Health check endpoint"""
    # Register component checks
    health_checker.register_check('scraper', True)
    health_checker.register_check('cache', concert_service.concerts_cache is not None)
    health_checker.register_check('geocoder', True)
    
    status = health_checker.get_status()
    status_code = 200 if status['status'] == 'healthy' else 503
    return jsonify(status), status_code


@app.route('/api/refresh', methods=['POST'])
def refresh_cache() -> jsonify:
    """API endpoint to force refresh cache"""
    # Optional: Add authentication check here
    api_key = request.headers.get('X-API-Key')
    expected_key = os.getenv('ADMIN_API_KEY')
    
    if expected_key and api_key != expected_key:
        return jsonify({'error': 'Unauthorized'}), 401
    
    success = concert_service.refresh_cache()
    if success:
        return jsonify({'status': 'success', 'message': 'Cache refreshed'})
    else:
        return jsonify({'status': 'error', 'message': 'Failed to refresh cache'}), 500


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({'error': 'Not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"Internal server error: {error}")
    return jsonify({'error': 'Internal server error'}), 500


if __name__ == '__main__':
    app_config = CONFIG.get('app', {})
    host = app_config.get('host', '0.0.0.0')
    port = int(app_config.get('port', 5000))
    debug = app_config.get('debug', False)
    
    logger.info(f"Starting server on {host}:{port}")
    logger.info(f"Debug mode: {debug}")
    
    # Register startup health check
    health_checker.register_check('startup', True)
    
    app.run(host=host, port=port, debug=debug)
