"""Explicit current-temperature answers using fresh modeled Open-Meteo data."""
import re
from pipeline.cities import LOCATIONS
from pipeline.contracts import WEATHER
from tools.api_tool import APITool


def answer_temperature(question, settings, *, api=None):
    if not re.search(r'\b(temp|temperature)\b', question, re.I):
        raise ValueError('Try: What is the current temperature in Bangalore?')
    text = re.sub(r'\b(bangalore|banglore)\b', 'Bengaluru', question, flags=re.I)
    cities = [city for city in LOCATIONS if re.search(r'\b' + city + r'\b', text, re.I)]
    if len(cities) != 1:
        raise ValueError('Please name one supported city: ' + ', '.join(LOCATIONS))
    city = cities[0]
    location = LOCATIONS[city]
    payload = (api or APITool(settings)).call_api(WEATHER, {
        'latitude': location['latitude'], 'longitude': location['longitude'],
        'current': 'temperature_2m', 'timezone': location['timezone']}, refresh=True)
    current = payload['current']
    value = current['temperature_2m']
    if not isinstance(value, (int, float)):
        raise ValueError('Current temperature is unavailable')
    return {'city': city, 'temperature': value, 'time': current['time'],
            'timezone': location['timezone'], 'unit': payload['current_units']['temperature_2m']}
