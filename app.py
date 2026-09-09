#!/usr/bin/env python3
"""
Web application that parses concerts from https://www.az0n.ru/main/live/
and displays them on a map with dates.
"""

import re
from flask import Flask, render_template_string, jsonify
import requests
from bs4 import BeautifulSoup
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable

app = Flask(__name__)

# Cache for geocoding results to avoid repeated API calls
geocode_cache = {}

def get_concerts():
    """Parse concerts from the website and extract date and city."""
    url = "https://www.az0n.ru/main/live/"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error fetching page: {e}")
        return []
    
    soup = BeautifulSoup(response.text, 'html.parser')
    concerts = []
    
    # Find all links with concert information
    # The pattern is: DD.MM.YYYY — City, Venue...
    date_city_pattern = re.compile(r'(\d{2}\.\d{2}\.\d{4})\s*—\s*([^,]+),')
    
    # Look for h3 tags with show class (upcoming concerts)
    for h3 in soup.find_all('h3', class_='show'):
        link = h3.find('a', class_='image_link')
        if link and link.text:
            match = date_city_pattern.search(link.text)
            if match:
                date = match.group(1)
                city = match.group(2).strip()
                concerts.append({'date': date, 'city': city})
    
    # Also look for past concerts (olink class)
    for a in soup.find_all('a', class_='olink image_link'):
        if a.text:
            match = date_city_pattern.search(a.text)
            if match:
                date = match.group(1)
                city = match.group(2).strip()
                # Check if this concert is already added
                if not any(c['date'] == date and c['city'] == city for c in concerts):
                    concerts.append({'date': date, 'city': city})
    
    return concerts


def geocode_city(city):
    """Get coordinates for a city using geopy."""
    if city in geocode_cache:
        return geocode_cache[city]
    
    try:
        # Add Russia to improve accuracy
        query = f"{city}, Россия"
        geolocator = Nominatim(user_agent="azon_concerts_app", timeout=5)
        location = geolocator.geocode(query, language='ru')
        
        if location:
            coords = (location.latitude, location.longitude)
            geocode_cache[city] = coords
            return coords
    except (GeocoderTimedOut, GeocoderUnavailable) as e:
        print(f"Geocoding error for {city}: {e}")
    
    geocode_cache[city] = None
    return None


@app.route('/')
def index():
    """Main page with the map."""
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/concerts')
def get_concerts_api():
    """API endpoint to get concerts with coordinates."""
    concerts = get_concerts()
    
    # Add coordinates to each concert
    result = []
    for concert in concerts:
        coords = geocode_city(concert['city'])
        if coords:
            result.append({
                'date': concert['date'],
                'city': concert['city'],
                'lat': coords[0],
                'lng': coords[1]
            })
    
    return jsonify(result)


HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Карта концертов группы АЗОН</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: Arial, sans-serif;
            background: #1a1a2e;
            color: #eee;
        }
        header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            text-align: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.3);
        }
        header h1 {
            font-size: 2em;
            margin-bottom: 10px;
        }
        header p {
            opacity: 0.9;
        }
        #map-container {
            display: flex;
            height: calc(100vh - 120px);
        }
        #map {
            flex: 1;
            height: 100%;
        }
        #sidebar {
            width: 350px;
            background: #16213e;
            overflow-y: auto;
            border-left: 2px solid #667eea;
        }
        .concert-item {
            padding: 15px;
            border-bottom: 1px solid #2a2a4a;
            cursor: pointer;
            transition: background 0.3s;
        }
        .concert-item:hover {
            background: #1f3460;
        }
        .concert-date {
            color: #667eea;
            font-weight: bold;
            font-size: 1.1em;
        }
        .concert-city {
            margin-top: 5px;
            font-size: 1.2em;
        }
        .loading {
            text-align: center;
            padding: 50px;
            color: #888;
        }
        .marker-popup {
            min-width: 150px;
        }
        .marker-popup .popup-date {
            color: #667eea;
            font-weight: bold;
            font-size: 1.1em;
        }
        @media (max-width: 768px) {
            #map-container {
                flex-direction: column;
            }
            #sidebar {
                width: 100%;
                height: 200px;
                border-left: none;
                border-top: 2px solid #667eea;
            }
        }
    </style>
</head>
<body>
    <header>
        <h1>🎸 Карта концертов группы АЗОН</h1>
        <p>Даты и города предстоящих выступлений</p>
    </header>
    
    <div id="map-container">
        <div id="map"></div>
        <div id="sidebar">
            <div class="loading">Загрузка концертов...</div>
        </div>
    </div>

    <script>
        // Initialize map centered on Russia
        const map = L.map('map').setView([55.7558, 37.6173], 5);
        
        // Add tile layer (dark theme)
        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
            subdomains: 'abcd',
            maxZoom: 19
        }).addTo(map);
        
        const markers = [];
        const sidebar = document.getElementById('sidebar');
        
        // Custom marker icon
        const concertIcon = L.divIcon({
            className: 'custom-marker',
            html: '<div style="background-color: #e94560; width: 20px; height: 20px; border-radius: 50%; border: 3px solid white; box-shadow: 0 2px 5px rgba(0,0,0,0.5);"></div>',
            iconSize: [20, 20],
            iconAnchor: [10, 10]
        });
        
        function loadConcerts() {
            fetch('/api/concerts')
                .then(response => response.json())
                .then(concerts => {
                    sidebar.innerHTML = '';
                    
                    if (concerts.length === 0) {
                        sidebar.innerHTML = '<div class="loading">Концерты не найдены</div>';
                        return;
                    }
                    
                    // Group concerts by city
                    const cityConcerts = {};
                    concerts.forEach(concert => {
                        if (!cityConcerts[concert.city]) {
                            cityConcerts[concert.city] = [];
                        }
                        cityConcerts[concert.city].push(concert);
                    });
                    
                    // Add markers and sidebar items
                    Object.keys(cityConcerts).forEach(city => {
                        const cityData = cityConcerts[city];
                        const firstConcert = cityData[0];
                        
                        // Create marker
                        const marker = L.marker([firstConcert.lat, firstConcert.lng], {icon: concertIcon})
                            .addTo(map);
                        
                        // Create popup with all dates for this city
                        let popupContent = '<div class="marker-popup">';
                        popupContent += `<strong>${city}</strong><br>`;
                        cityData.forEach(c => {
                            popupContent += `<div class="popup-date">${c.date}</div>`;
                        });
                        popupContent += '</div>';
                        
                        marker.bindPopup(popupContent);
                        markers.push({marker, city, lat: firstConcert.lat, lng: firstConcert.lng});
                        
                        // Add to sidebar
                        const item = document.createElement('div');
                        item.className = 'concert-item';
                        item.innerHTML = `
                            <div class="concert-date">${cityData.map(c => c.date).join(', ')}</div>
                            <div class="concert-city">📍 ${city}</div>
                        `;
                        item.addEventListener('click', () => {
                            map.setView([firstConcert.lat, firstConcert.lng], 10);
                            marker.openPopup();
                        });
                        sidebar.appendChild(item);
                    });
                })
                .catch(error => {
                    console.error('Error loading concerts:', error);
                    sidebar.innerHTML = '<div class="loading">Ошибка загрузки данных</div>';
                });
        }
        
        loadConcerts();
    </script>
</body>
</html>
'''


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
