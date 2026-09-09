#!/usr/bin/env python3
"""
Web application that parses concerts from https://www.az0n.ru/main/live/
and displays them on a map with dates.1
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
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: #f5f7fa;
            color: #2d3748;
        }
        header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 24px 20px;
            text-align: center;
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.25);
        }
        header h1 {
            font-size: 1.75em;
            font-weight: 700;
            margin-bottom: 8px;
            color: #ffffff;
            letter-spacing: -0.5px;
        }
        header p {
            opacity: 0.95;
            font-size: 0.95em;
            color: rgba(255, 255, 255, 0.9);
            font-weight: 400;
        }
        #map-container {
            display: flex;
            height: calc(100vh - 100px);
            gap: 0;
        }
        #map {
            flex: 1;
            height: 100%;
            background: #e8ecf1;
        }
        #sidebar {
            width: 380px;
            background: #ffffff;
            overflow-y: auto;
            border-left: 1px solid #e2e8f0;
            box-shadow: -4px 0 15px rgba(0, 0, 0, 0.04);
        }
        #sidebar::-webkit-scrollbar {
            width: 6px;
        }
        #sidebar::-webkit-scrollbar-track {
            background: #f1f5f9;
        }
        #sidebar::-webkit-scrollbar-thumb {
            background: #cbd5e1;
            border-radius: 3px;
        }
        #sidebar::-webkit-scrollbar-thumb:hover {
            background: #94a3b8;
        }
        .concert-item {
            padding: 18px 20px;
            border-bottom: 1px solid #f1f5f9;
            cursor: pointer;
            transition: all 0.2s ease;
            background: #ffffff;
        }
        .concert-item:hover {
            background: #f8fafc;
            border-left: 3px solid #667eea;
            padding-left: 17px;
        }
        .concert-date {
            color: #667eea;
            font-weight: 600;
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 6px;
        }
        .concert-city {
            font-size: 1.15em;
            font-weight: 500;
            color: #1a202c;
        }
        .loading {
            text-align: center;
            padding: 60px 20px;
            color: #718096;
            font-size: 0.95em;
        }
        .marker-popup {
            min-width: 160px;
        }
        .marker-popup strong {
            display: block;
            margin-bottom: 10px;
            color: #2d3748;
            font-size: 1.1em;
        }
        .marker-popup .popup-date {
            color: #667eea;
            font-weight: 600;
            font-size: 0.95em;
            padding: 4px 0;
            border-bottom: 1px dashed #e2e8f0;
        }
        .marker-popup .popup-date:last-child {
            border-bottom: none;
        }
        @media (max-width: 768px) {
            #map-container {
                flex-direction: column;
            }
            #sidebar {
                width: 100%;
                height: 220px;
                border-left: none;
                border-top: 1px solid #e2e8f0;
            }
            header h1 {
                font-size: 1.4em;
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
        
        // Add tile layer (light theme)
        L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
            subdomains: 'abcd',
            maxZoom: 19
        }).addTo(map);
        
        const markers = [];
        const sidebar = document.getElementById('sidebar');
        
        // Custom marker icon with modern design
        const concertIcon = L.divIcon({
            className: 'custom-marker',
            html: '<div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); width: 24px; height: 24px; border-radius: 50%; border: 3px solid white; box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4); transition: transform 0.2s;"></div>',
            iconSize: [24, 24],
            iconAnchor: [12, 12]
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
                    
                    // Sort cities by first date
                    const sortedCities = Object.keys(cityConcerts).sort((a, b) => {
                        const dateA = cityConcerts[a][0].date.split('.').reverse().join('');
                        const dateB = cityConcerts[b][0].date.split('.').reverse().join('');
                        return dateA.localeCompare(dateB);
                    });
                    
                    // Add markers and sidebar items
                    sortedCities.forEach(city => {
                        const cityData = cityConcerts[city];
                        const firstConcert = cityData[0];
                        
                        // Create marker
                        const marker = L.marker([firstConcert.lat, firstConcert.lng], {icon: concertIcon})
                            .addTo(map);
                        
                        // Create popup with all dates for this city
                        let popupContent = '<div class="marker-popup">';
                        popupContent += `<strong>📍 ${city}</strong>`;
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
                            <div class="concert-city">${city}</div>
                        `;
                        item.addEventListener('click', () => {
                            map.setView([firstConcert.lat, firstConcert.lng], 10, {
                                animate: true,
                                duration: 0.5
                            });
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
