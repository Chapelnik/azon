#!/usr/bin/env python3
"""
Web application that parses concerts from https://www.az0n.ru/main/live/
and displays them on a map with dates.
"""

import os
import re
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, render_template_string, jsonify
import requests
from bs4 import BeautifulSoup
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable

# Load configuration
def load_config():
    config_path = Path(__file__).parent / 'config.json'
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

CONFIG = load_config()

# Setup logging
def setup_logging():
    log_config = CONFIG.get('logging', {})
    log_level = getattr(logging, log_config.get('level', 'INFO'), logging.INFO)
    log_file = log_config.get('file', 'logs/app.log')
    log_format = log_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    log_dir = Path(log_file).parent
    log_dir.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logging()

app = Flask(__name__)

CACHE_DIR = Path('.cache')
CACHE_DIR.mkdir(exist_ok=True)

class FileCache:
    def __init__(self, cache_file, ttl_hours=24):
        self.cache_file = Path(cache_file)
        self.ttl = timedelta(hours=ttl_hours)
        self.data = self._load()
    
    def _load(self):
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
    
    def save(self, content):
        try:
            data = {'timestamp': datetime.now().isoformat(), 'content': content}
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved cache to {self.cache_file}")
        except Exception as e:
            logger.error(f"Error saving cache: {e}")
    
    def get(self):
        return self.data
    
    def is_valid(self):
        if not self.cache_file.exists():
            return False
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                cached_time = datetime.fromisoformat(data.get('timestamp', '1970-01-01'))
                return datetime.now() - cached_time < self.ttl
        except:
            return False

cache_config = CONFIG.get('cache', {})
concerts_cache = FileCache(
    cache_config.get('file_path', '.cache/concerts_cache.json'),
    cache_config.get('ttl_hours', 24)
) if cache_config.get('enabled', True) else None

geocode_cache_file = Path('.cache/geocode_cache.json')
geocode_cache = {}
if geocode_cache_file.exists():
    try:
        with open(geocode_cache_file, 'r', encoding='utf-8') as f:
            geocode_cache = json.load(f)
    except:
        pass

def save_geocode_cache():
    try:
        with open(geocode_cache_file, 'w', encoding='utf-8') as f:
            json.dump(geocode_cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error saving geocode cache: {e}")

stats = {
    'total_requests': 0,
    'cache_hits': 0,
    'cache_misses': 0,
    'parse_errors': 0,
    'geocode_errors': 0,
    'last_updated': None
}

def get_concerts(force_refresh=False):
    global stats
    stats['total_requests'] += 1
    
    if concerts_cache and not force_refresh and concerts_cache.is_valid():
        stats['cache_hits'] += 1
        logger.info("Using cached concerts data")
        return concerts_cache.get()
    
    stats['cache_misses'] += 1
    logger.info("Fetching fresh concerts data")
    
    url = "https://www.az0n.ru/main/live/"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Error fetching page: {e}")
        stats['parse_errors'] += 1
        return []
    
    soup = BeautifulSoup(response.text, 'html.parser')
    concerts = []
    date_city_pattern = re.compile(r'(\d{2}\.\d{2}\.\d{4})\s*—\s*([^,]+),')
    
    for h3 in soup.find_all('h3', class_='show'):
        link = h3.find('a', class_='image_link')
        if link and link.text:
            match = date_city_pattern.search(link.text)
            if match:
                concerts.append({'date': match.group(1), 'city': match.group(2).strip()})
    
    for a in soup.find_all('a', class_='olink image_link'):
        if a.text:
            match = date_city_pattern.search(a.text)
            if match:
                date, city = match.group(1), match.group(2).strip()
                if not any(c['date'] == date and c['city'] == city for c in concerts):
                    concerts.append({'date': date, 'city': city})
    
    if concerts_cache:
        concerts_cache.save(concerts)
    
    stats['last_updated'] = datetime.now().isoformat()
    logger.info(f"Parsed {len(concerts)} concerts")
    return concerts

def geocode_city(city):
    if city in geocode_cache:
        return geocode_cache[city]
    try:
        geolocator = Nominatim(user_agent="azon_concerts_app", timeout=5)
        location = geolocator.geocode(f"{city}, Россия", language='ru')
        if location:
            coords = (location.latitude, location.longitude)
            geocode_cache[city] = coords
            save_geocode_cache()
            logger.info(f"Geocoded '{city}' -> {coords}")
            return coords
    except (GeocoderTimedOut, GeocoderUnavailable) as e:
        logger.error(f"Geocoding error for {city}: {e}")
        stats['geocode_errors'] += 1
    geocode_cache[city] = None
    save_geocode_cache()
    return None

@app.route('/')
def index():
    carto_config = CONFIG.get('carto', {})
    api_key = carto_config.get('api_key', '')
    username = carto_config.get('username', '')
    return render_template_string(HTML_TEMPLATE, api_key=api_key, username=username)

@app.route('/api/concerts')
def get_concerts_api():
    concerts = get_concerts()
    result = []
    cities_processed = set()
    for concert in concerts:
        if concert['city'] in cities_processed:
            continue
        cities_processed.add(concert['city'])
        coords = geocode_city(concert['city'])
        if coords:
            result.append({**concert, 'lat': coords[0], 'lng': coords[1]})
    logger.info(f"API returned {len(result)} concerts with coordinates")
    return jsonify(result)

@app.route('/api/stats')
def get_stats():
    return jsonify({**stats, 'cache_enabled': concerts_cache is not None, 'geocode_cache_size': len(geocode_cache)})

HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Карта концертов группы АЗОН</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
    <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css" />
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Inter', sans-serif; background: #f5f7fa; color: #2d3748; }
        header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 24px 20px; text-align: center; box-shadow: 0 4px 15px rgba(102, 126, 234, 0.25); }
        header h1 { font-size: 1.75em; font-weight: 700; margin-bottom: 8px; color: #fff; letter-spacing: -0.5px; }
        header p { opacity: 0.95; font-size: 0.95em; color: rgba(255,255,255,0.9); font-weight: 400; }
        .stats-bar { background: #fff; padding: 12px 20px; display: flex; justify-content: center; gap: 24px; border-bottom: 1px solid #e2e8f0; font-size: 0.85em; color: #64748b; }
        .stat-item { display: flex; align-items: center; gap: 6px; }
        .stat-value { font-weight: 600; color: #667eea; }
        #map-container { display: flex; height: calc(100vh - 140px); }
        #map { flex: 1; height: 100%; background: #e8ecf1; }
        #sidebar { width: 380px; background: #fff; overflow-y: auto; border-left: 1px solid #e2e8f0; box-shadow: -4px 0 15px rgba(0,0,0,0.04); }
        #sidebar::-webkit-scrollbar { width: 6px; }
        #sidebar::-webkit-scrollbar-track { background: #f1f5f9; }
        #sidebar::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 3px; }
        #sidebar::-webkit-scrollbar-thumb:hover { background: #94a3b8; }
        .concert-item { padding: 18px 20px; border-bottom: 1px solid #f1f5f9; cursor: pointer; transition: all 0.2s ease; background: #fff; }
        .concert-item:hover { background: #f8fafc; border-left: 3px solid #667eea; padding-left: 17px; }
        .concert-date { color: #667eea; font-weight: 600; font-size: 0.9em; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; }
        .concert-city { font-size: 1.15em; font-weight: 500; color: #1a202c; }
        .loading { text-align: center; padding: 60px 20px; color: #718096; font-size: 0.95em; }
        .marker-popup { min-width: 160px; }
        .marker-popup strong { display: block; margin-bottom: 10px; color: #2d3748; font-size: 1.1em; }
        .marker-popup .popup-date { color: #667eea; font-weight: 600; font-size: 0.95em; padding: 4px 0; border-bottom: 1px dashed #e2e8f0; }
        .marker-popup .popup-date:last-child { border-bottom: none; }
        .marker-cluster-small { background-color: rgba(102, 126, 234, 0.4); }
        .marker-cluster-small div { background-color: rgba(102, 126, 234, 0.8); color: white; font-weight: 600; }
        .marker-cluster-medium { background-color: rgba(118, 75, 162, 0.4); }
        .marker-cluster-medium div { background-color: rgba(118, 75, 162, 0.8); color: white; font-weight: 600; }
        .marker-cluster-large { background-color: rgba(147, 51, 234, 0.4); }
        .marker-cluster-large div { background-color: rgba(147, 51, 234, 0.8); color: white; font-weight: 600; }
        @media (max-width: 768px) { #map-container { flex-direction: column; } #sidebar { width: 100%; height: 220px; border-left: none; border-top: 1px solid #e2e8f0; } header h1 { font-size: 1.4em; } .stats-bar { flex-wrap: wrap; gap: 12px; } }
    </style>
</head>
<body>
    <header><h1>🎸 Карта концертов группы АЗОН</h1><p>Даты и города предстоящих выступлений</p></header>
    <div class="stats-bar">
        <div class="stat-item">Концертов: <span class="stat-value" id="stat-count">0</span></div>
        <div class="stat-item">Городов: <span class="stat-value" id="stat-cities">0</span></div>
        <div class="stat-item">Кэш: <span class="stat-value" id="stat-cache">-</span></div>
    </div>
    <div id="map-container"><div id="map"></div><div id="sidebar"><div class="loading">Загрузка концертов...</div></div></div>
    <script>
        const map = L.map('map').setView([55.7558, 37.6173], 5);
        const apiKey = "{{ api_key }}" || "";
        let tileUrl = apiKey ? `https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png?api_key=${apiKey}` : "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png";
        L.tileLayer(tileUrl, { attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>', subdomains: 'abcd', maxZoom: 19 }).addTo(map);
        
        const markers = L.markerClusterGroup({ showCoverageOnHover: false, maxClusterRadius: 50, spiderfyOnMaxZoom: true });
        map.addLayer(markers);
        
        const sidebar = document.getElementById('sidebar');
        const concertIcon = L.divIcon({ className: 'custom-marker', html: '<div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); width: 20px; height: 20px; border-radius: 50%; border: 3px solid white; box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);"></div>', iconSize: [20, 20], iconAnchor: [10, 10] });
        
        function updateStats(count, cities) { document.getElementById('stat-count').textContent = count; document.getElementById('stat-cities').textContent = cities; }
        
        fetch('/api/concerts').then(r => r.json()).then(concerts => {
            sidebar.innerHTML = '';
            if (!concerts.length) { sidebar.innerHTML = '<div class="loading">Концерты не найдены</div>'; updateStats(0, 0); return; }
            
            const cityConcerts = {};
            concerts.forEach(c => { if (!cityConcerts[c.city]) cityConcerts[c.city] = []; cityConcerts[c.city].push(c); });
            updateStats(concerts.length, Object.keys(cityConcerts).length);
            
            Object.keys(cityConcerts).sort((a, b) => cityConcerts[a][0].date.split('.').reverse().join('').localeCompare(cityConcerts[b][0].date.split('.').reverse().join(''))).forEach(city => {
                const cityData = cityConcerts[city];
                const marker = L.marker([cityData[0].lat, cityData[0].lng], {icon: concertIcon});
                let popup = '<div class="marker-popup"><strong>📍 ' + city + '</strong>';
                cityData.forEach(c => popup += '<div class="popup-date">' + c.date + '</div>');
                popup += '</div>';
                marker.bindPopup(popup);
                markers.addLayer(marker);
                
                const item = document.createElement('div');
                item.className = 'concert-item';
                item.innerHTML = '<div class="concert-date">' + cityData.map(c => c.date).join(', ') + '</div><div class="concert-city">' + city + '</div>';
                item.onclick = () => { map.setView([cityData[0].lat, cityData[0].lng], 10, {animate: true, duration: 0.5}); marker.openPopup(); };
                sidebar.appendChild(item);
            });
        }).catch(e => { console.error(e); sidebar.innerHTML = '<div class="loading">Ошибка загрузки данных</div>'; });
        
        fetch('/api/stats').then(r => r.json()).then(s => { document.getElementById('stat-cache').textContent = s.cache_enabled ? 'Вкл' : 'Выкл'; }).catch(() => {});
    </script>
</body>
</html>'''

if __name__ == '__main__':
    app_config = CONFIG.get('app', {})
    host = app_config.get('host', '0.0.0.0')
    port = app_config.get('port', 5000)
    debug = app_config.get('debug', False)
    logger.info(f"Starting server on {host}:{port}")
    app.run(host=host, port=port, debug=debug)
