"""
Test suite for concert scraper application
"""

import pytest
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Import modules to test
from scraper import ConcertScraper
from cache import FileCache, GeocodeCache
from geocoder import RateLimiter, GeocoderService


class TestConcertScraper:
    """Tests for ConcertScraper class"""
    
    @pytest.fixture
    def scraper(self):
        return ConcertScraper(timeout=5, max_retries=1)
    
    def test_date_validation_valid(self, scraper):
        """Test date validation with valid dates"""
        # Future date should be valid
        future_date = (datetime.now() + timedelta(days=30)).strftime('%d.%m.%Y')
        assert scraper.validate_date(future_date) is True
        
        # Today should be valid
        today = datetime.now().strftime('%d.%m.%Y')
        assert scraper.validate_date(today) is True
        
        # Recent past (within buffer) should be valid
        recent_past = (datetime.now() - timedelta(days=5)).strftime('%d.%m.%Y')
        assert scraper.validate_date(recent_past) is True
        
        # Date in near future (like 15.12.2025 when it's late 2025) should be valid
        # Use a date that's always in the future relative to now
        next_year = (datetime.now().replace(year=datetime.now().year + 1)).strftime('%d.%m.%Y')
        assert scraper.validate_date(next_year) is True
    
    def test_parse_concerts_basic(self, scraper):
        """Test basic concert parsing"""
        # Use a date that will be valid (in the future)
        future_date = (datetime.now() + timedelta(days=30)).strftime('%d.%m.%Y')
        html = f'''
        <html>
            <h3 class="show">
                <a class="image_link">{future_date} — Москва, концерт</a>
            </h3>
        </html>
        '''
        concerts = scraper.parse_concerts(html)
        assert len(concerts) == 1
        assert concerts[0]['date'] == future_date
        assert concerts[0]['city'] == 'Москва'
    
    def test_parse_concerts_duplicates(self, scraper):
        """Test that duplicates are removed"""
        future_date = (datetime.now() + timedelta(days=30)).strftime('%d.%m.%Y')
        html = f'''
        <html>
            <h3 class="show">
                <a class="image_link">{future_date} — Москва, концерт</a>
            </h3>
            <a class="olink image_link">{future_date} — Москва, дубликат</a>
        </html>
        '''
        concerts = scraper.parse_concerts(html)
        assert len(concerts) == 1
    
    def test_date_validation_invalid(self, scraper):
        """Test date validation with invalid dates"""
        # Old date should be invalid
        old_date = '01.01.2020'
        assert scraper.validate_date(old_date) is False
        
        # Invalid format should be invalid
        assert scraper.validate_date('invalid') is False
        assert scraper.validate_date('2024-01-01') is False
    
    def test_city_validation_valid(self, scraper):
        """Test city validation with valid cities"""
        assert scraper.validate_city('Москва') is True
        assert scraper.validate_city('санкт-петербург') is True
        assert scraper.validate_city('Екатеринбург') is True
    
    def test_city_validation_invalid(self, scraper):
        """Test city validation with invalid cities"""
        assert scraper.validate_city('') is False
        assert scraper.validate_city('A') is False
        assert scraper.validate_city('UnknownCity123') is False
    
    def test_parse_concerts_empty(self, scraper):
        """Test parsing empty HTML"""
        assert scraper.parse_concerts('') == []
        assert scraper.parse_concerts(None) == []
    
    def test_parse_concerts_basic(self, scraper):
        """Test basic concert parsing"""
        html = '''
        <html>
            <h3 class="show">
                <a class="image_link">15.12.2025 — Москва, концерт</a>
            </h3>
        </html>
        '''
        concerts = scraper.parse_concerts(html)
        assert len(concerts) == 1
        assert concerts[0]['date'] == '15.12.2025'
        assert concerts[0]['city'] == 'Москва'
    
    def test_parse_concerts_duplicates(self, scraper):
        """Test that duplicates are removed"""
        html = '''
        <html>
            <h3 class="show">
                <a class="image_link">15.12.2025 — Москва, концерт</a>
            </h3>
            <a class="olink image_link">15.12.2025 — Москва, дубликат</a>
        </html>
        '''
        concerts = scraper.parse_concerts(html)
        assert len(concerts) == 1
    
    @patch('scraper.requests.Session')
    def test_fetch_page_success(self, mock_session, scraper):
        """Test successful page fetch"""
        mock_response = Mock()
        mock_response.text = '<html>content</html>'
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        
        session_instance = Mock()
        session_instance.get.return_value = mock_response
        mock_session.return_value = session_instance
        
        result = scraper.fetch_page()
        assert result == '<html>content</html>'
    
    @patch('scraper.requests.Session')
    def test_fetch_page_failure(self, mock_session, scraper):
        """Test failed page fetch"""
        import requests
        session_instance = Mock()
        session_instance.get.side_effect = requests.RequestException("Network error")
        mock_session.return_value = session_instance
        
        result = scraper.fetch_page()
        assert result is None


class TestFileCache:
    """Tests for FileCache class"""
    
    @pytest.fixture
    def cache_file(self, tmp_path):
        return str(tmp_path / 'test_cache.json')
    
    @pytest.fixture
    def cache(self, cache_file):
        return FileCache(cache_file, ttl_hours=24)
    
    def test_cache_save_and_load(self, cache, cache_file):
        """Test saving and loading cache"""
        data = [{'date': '15.12.2025', 'city': 'Москва'}]
        cache.save(data)
        
        # Reload cache
        new_cache = FileCache(cache_file, ttl_hours=24)
        assert new_cache.get() == data
    
    def test_cache_is_valid(self, cache):
        """Test cache validity check"""
        assert cache.is_valid() is False  # Empty cache
        
        cache.save([{'test': 'data'}])
        assert cache.is_valid() is True
    
    def test_cache_clear(self, cache, cache_file):
        """Test cache clearing"""
        cache.save([{'test': 'data'}])
        result = cache.clear()
        
        assert result is True
        assert cache.get() == []
        assert Path(cache_file).exists() is False
    
    def test_cache_ttl_expiration(self, tmp_path):
        """Test cache TTL expiration"""
        cache_file = tmp_path / 'expired_cache.json'
        cache = FileCache(str(cache_file), ttl_hours=0)  # Immediate expiration
        
        cache.save([{'test': 'data'}])
        
        # Cache should be expired immediately
        import time
        time.sleep(0.1)
        
        new_cache = FileCache(str(cache_file), ttl_hours=0)
        assert new_cache.get() == []


class TestGeocodeCache:
    """Tests for GeocodeCache class"""
    
    @pytest.fixture
    def cache_file(self, tmp_path):
        return str(tmp_path / 'geocode_cache.json')
    
    @pytest.fixture
    def cache(self, cache_file):
        return GeocodeCache(cache_file)
    
    def test_cache_set_get(self, cache):
        """Test setting and getting coordinates"""
        coords = (55.7558, 37.6173)
        cache.set('москва', coords)
        
        assert cache.get('москва') == coords
    
    def test_cache_persistence(self, cache, cache_file):
        """Test cache persistence across instances"""
        cache.set('москва', (55.7558, 37.6173))
        
        # New instance should load cached data
        new_cache = GeocodeCache(cache_file)
        assert new_cache.get('москва') == (55.7558, 37.6173)
    
    def test_cache_size(self, cache):
        """Test cache size tracking"""
        assert cache.size() == 0
        
        cache.set('москва', (55.7558, 37.6173))
        cache.set('спб', (59.9343, 30.3351))
        
        assert cache.size() == 2


class TestRateLimiter:
    """Tests for RateLimiter class"""
    
    def test_rate_limiter_initialization(self):
        """Test rate limiter initialization"""
        limiter = RateLimiter(calls_per_second=2.0)
        assert limiter.min_interval == 0.5
    
    def test_rate_limiter_wait(self):
        """Test rate limiter waiting"""
        import time
        
        limiter = RateLimiter(calls_per_second=10.0)  # 0.1 second interval
        
        # First call should not wait
        start = time.time()
        limiter.wait()
        first_call_time = time.time() - start
        assert first_call_time < 0.05
        
        # Second call should wait
        start = time.time()
        limiter.wait()
        wait_time = time.time() - start
        assert wait_time >= 0.05  # Should wait at least 0.1 seconds (with some tolerance)


class TestGeocoderService:
    """Tests for GeocoderService class"""
    
    @pytest.fixture
    def geocode_cache(self, tmp_path):
        from cache import GeocodeCache
        return GeocodeCache(str(tmp_path / 'geo_cache.json'))
    
    @pytest.fixture
    def geocoder(self, geocode_cache):
        return GeocoderService(geocode_cache, timeout=2, max_retries=0)
    
    def test_known_cities(self, geocoder):
        """Test known cities fallback"""
        coords = geocoder.geocode('москва')
        assert coords == (55.7558, 37.6173)
    
    def test_normalize_city(self, geocoder):
        """Test city name normalization"""
        assert geocoder._normalize_city('  МОСКВА  ') == 'москва'
        assert geocoder._normalize_city('Санкт-Петербург') == 'санкт-петербург'
    
    def test_stats_tracking(self, geocoder):
        """Test statistics tracking"""
        geocoder.geocode('москва')  # Should use known cities
        
        stats = geocoder.get_stats()
        assert stats['total_requests'] >= 1
        assert stats['cache_hits'] >= 1  # Known cities count as cache hits


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
