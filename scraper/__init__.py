"""
Scraper module for parsing concert data from az0n.ru
"""

import re
import logging
from datetime import datetime
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class ConcertScraper:
    """Scraper for parsing concert data from az0n.ru"""
    
    VALID_CITIES = {
        'москва', 'санкт-петербург', 'новосибирск', 'екатеринбург', 'казань',
        'нижний новгород', 'челябинск', 'самара', 'омск', 'ростов-на-дону',
        'уфа', 'красноярск', 'воронеж', 'пермь', 'волгоград', 'краснодар',
        'саратов', 'тюмень', 'тольятти', 'ижевск', 'барнаул', 'ульяновск',
        'иркутск', 'хабаровск', 'ярославль', 'владивосток', 'махачкала',
        'томск', 'оренбург', 'кемерово', 'новокузнецк', 'рязань', 'астрахань',
        'пенза', 'липецк', 'киров', 'тула', 'чебоксары', 'калининград',
        'брянск', 'курск', 'иваново', 'тверь', 'ставрополь', 'белгород',
        'соchi', 'нижний тагил', 'владимир', 'архангельск', 'чита', 'смоленск',
        'волжский', 'курган', 'орёл', 'череповец', 'петрозаводск', 'сыктывкар',
        'мурманск', 'саранск', 'тамбов', 'грозный', 'стерлитамак', 'йошкар-ола'
    }
    
    def __init__(self, timeout: int = 10, max_retries: int = 3):
        self.timeout = timeout
        self.session = self._create_session(max_retries)
        self.url = "https://www.az0n.ru/main/live/"
        self.date_city_pattern = re.compile(r'(\d{2}\.\d{2}\.\d{4})\s*—\s*([^,]+),')
    
    def _create_session(self, max_retries: int) -> requests.Session:
        """Create a session with retry logic"""
        session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1.0,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session
    
    def fetch_page(self) -> Optional[str]:
        """Fetch the page content with retry logic"""
        try:
            logger.info(f"Fetching page: {self.url}")
            response = self.session.get(self.url, timeout=self.timeout)
            response.raise_for_status()
            logger.info(f"Successfully fetched page, status: {response.status_code}")
            return response.text
        except requests.RequestException as e:
            logger.error(f"Error fetching page: {e}")
            return None
    
    def validate_date(self, date_str: str) -> bool:
        """Validate date format and ensure it's not in the past"""
        try:
            concert_date = datetime.strptime(date_str, '%d.%m.%Y')
            # Allow concerts from today onwards (with some buffer for parsing errors)
            min_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            min_date = min_date.replace(day=min_date.day - 7)  # 7 days buffer
            return concert_date >= min_date
        except ValueError:
            return False
    
    def validate_city(self, city: str) -> bool:
        """Validate city name"""
        if not city or len(city.strip()) < 2:
            return False
        return city.lower() in self.VALID_CITIES
    
    def parse_concerts(self, html_content: str) -> List[Dict[str, str]]:
        """Parse concert data from HTML content"""
        if not html_content:
            return []
        
        soup = BeautifulSoup(html_content, 'html.parser')
        concerts = []
        seen = set()
        
        # Parse from h3.show elements
        for h3 in soup.find_all('h3', class_='show'):
            link = h3.find('a', class_='image_link')
            if link and link.text:
                match = self.date_city_pattern.search(link.text)
                if match:
                    date_str, city = match.group(1), match.group(2).strip()
                    key = f"{date_str}_{city}"
                    if key not in seen:
                        if self.validate_date(date_str) and self.validate_city(city):
                            concerts.append({'date': date_str, 'city': city})
                            seen.add(key)
                        else:
                            if not self.validate_date(date_str):
                                logger.warning(f"Invalid date: {date_str}")
                            if not self.validate_city(city):
                                logger.warning(f"Invalid city: {city}")
        
        # Parse from a.olink.image_link elements
        for a in soup.find_all('a', class_='olink image_link'):
            if a.text:
                match = self.date_city_pattern.search(a.text)
                if match:
                    date_str, city = match.group(1), match.group(2).strip()
                    key = f"{date_str}_{city}"
                    if key not in seen:
                        if self.validate_date(date_str) and self.validate_city(city):
                            concerts.append({'date': date_str, 'city': city})
                            seen.add(key)
        
        logger.info(f"Parsed {len(concerts)} valid concerts")
        return concerts
    
    def get_concerts(self) -> List[Dict[str, str]]:
        """Main method to fetch and parse concerts"""
        html = self.fetch_page()
        if html is None:
            return []
        return self.parse_concerts(html)
