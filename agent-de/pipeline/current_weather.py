"""Explicit current-temperature answers using fresh modeled Open-Meteo data."""
import re
from pipeline.cities import LOCATIONS
from pipeline.contracts import WEATHER
from tools.api_tool import APITool


def answer_temperature(question, settings, *, api=None, default_city=None):
    """Return current weather details; legacy name retained for callers."""
    if re.search(r'\b(tomorrow|yesterday|forecast|next week)\b', question, re.I):
        raise ValueError('This field answers current weather. Forecast questions are not supported yet.')
    if not re.search(r'weather|wether|rain|temp|humidity|wind|cloud|snow|drizzl|condition|hot|cold|feels|sunny|sunshine|clear|overcast|fog|storm', question, re.I):
        raise ValueError('Ask about current weather, rain, temperature, humidity, clouds or wind.')
    text = re.sub(r'\b(bangalore|banglore)\b', 'Bengaluru', question, flags=re.I)
    cities = [city for city in LOCATIONS if re.search(r'\b' + city + r'\b', text, re.I)]
    if not cities and default_city in LOCATIONS and not re.search(r'\b(in|for|at)\s+\w+', text, re.I):
        cities = [default_city]
    if len(cities) != 1:
        raise ValueError('Please name one supported city: ' + ', '.join(LOCATIONS))
    city = cities[0]
    location = LOCATIONS[city]
    payload = (api or APITool(settings)).call_api(WEATHER, {
        'latitude': location['latitude'], 'longitude': location['longitude'],
        'current': 'temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,rain,showers,snowfall,weather_code,cloud_cover,is_day,wind_speed_10m,wind_direction_10m,wind_gusts_10m', 'timezone': location['timezone']}, refresh=True)
    current = payload['current']
    value = current['temperature_2m']
    if not isinstance(value, (int, float)):
        raise ValueError('Current temperature is unavailable')
    codes = {0: 'Clear sky', 1: 'Mainly clear', 2: 'Partly cloudy', 3: 'Overcast', 45: 'Fog', 48: 'Depositing rime fog', 51: 'Light drizzle', 53: 'Moderate drizzle', 55: 'Dense drizzle', 56: 'Light freezing drizzle', 57: 'Dense freezing drizzle', 61: 'Slight rain', 63: 'Moderate rain', 65: 'Heavy rain', 66: 'Light freezing rain', 67: 'Heavy freezing rain', 71: 'Slight snow', 73: 'Moderate snow', 75: 'Heavy snow', 77: 'Snow grains', 80: 'Slight rain showers', 81: 'Moderate rain showers', 82: 'Violent rain showers', 85: 'Slight snow showers', 86: 'Heavy snow showers', 95: 'Thunderstorm', 96: 'Thunderstorm with hail', 99: 'Thunderstorm with heavy hail'}
    rain = current.get('rain')
    showers = current.get('showers')
    rain_text = 'Rain data unavailable.' if rain is None or showers is None else ('Rain is indicated in the current modeled interval.' if rain + showers > 0 else 'No rain is indicated in the current modeled interval.')
    condition = codes.get(current.get('weather_code'), 'Conditions unavailable')
    direct = ''
    if re.search(r'sunny|sunshine', question, re.I):
        if current.get('is_day') == 0:
            direct = f'No—it is nighttime in {city}. '
        elif current.get('is_day') == 1 and current.get('weather_code') in (0, 1):
            direct = f'Yes—the current modeled conditions in {city} are clear or mainly clear during daylight. '
        elif current.get('is_day') == 1 and current.get('weather_code') == 2:
            direct = f'It is partly cloudy in {city}; there may be sunny intervals. '
        elif current.get('is_day') == 1 and current.get('weather_code') in codes:
            direct = f'The current model does not indicate clear sunny conditions in {city}. '
        else:
            direct = 'Sunshine conditions are unavailable in the current response. '
    details = []
    for field, label in [('relative_humidity_2m', 'Humidity'), ('apparent_temperature', 'Feels like'), ('wind_speed_10m', 'Wind'), ('cloud_cover', 'Cloud cover')]:
        if current.get(field) is not None:
            details.append(f"{label}: {current[field]} {payload['current_units'].get(field, '')}")
    return {'city': city, 'temperature': value, 'time': current['time'],
            'timezone': location['timezone'], 'unit': payload['current_units']['temperature_2m'],
            'current': current, 'units': payload['current_units'],
            'answer': direct + f'{city}: {condition}. Temperature {value:.1f} °C. {rain_text} ' + '. '.join(details)}
