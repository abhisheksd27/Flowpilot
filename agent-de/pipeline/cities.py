"""Supported Indian cities and independent city run records."""
import json
from config import Settings
from pipeline.events import write_json

# Coordinates verified against Open-Meteo geocoding on 2026-11-08.
# Stable catalog cities need no repeated network lookup on hourly runs.
LOCATIONS = {'Bengaluru': {'id': 1277333, 'name': 'Bengaluru', 'latitude': 12.97194, 'longitude': 77.59369, 'timezone': 'Asia/Kolkata', 'country': 'India', 'country_code': 'IN'}, 'Mumbai': {'id': 1275339, 'name': 'Mumbai', 'latitude': 19.07283, 'longitude': 72.88261, 'timezone': 'Asia/Kolkata', 'country': 'India', 'country_code': 'IN'}, 'Delhi': {'id': 1273294, 'name': 'Delhi', 'latitude': 28.65195, 'longitude': 77.23149, 'timezone': 'Asia/Kolkata', 'country': 'India', 'country_code': 'IN'}, 'Chennai': {'id': 1264527, 'name': 'Chennai', 'latitude': 13.08784, 'longitude': 80.27847, 'timezone': 'Asia/Kolkata', 'country': 'India', 'country_code': 'IN'}, 'Hyderabad': {'id': 1269843, 'name': 'Hyderabad', 'latitude': 17.38405, 'longitude': 78.45636, 'timezone': 'Asia/Kolkata', 'country': 'India', 'country_code': 'IN'}, 'Kolkata': {'id': 1275004, 'name': 'Kolkata', 'latitude': 22.56263, 'longitude': 88.36304, 'timezone': 'Asia/Kolkata', 'country': 'India', 'country_code': 'IN'}}
CITIES = tuple(LOCATIONS)


def city_request(city):
    if city not in CITIES:
        raise ValueError('Unsupported city')
    return f'Track daily weather and air quality for {city} and flag anomalies.'


def city_result(settings, city):
    city_request(city)
    path = settings.data_dir / 'cities' / f'{city.lower()}.json'
    saved = json.loads(path.read_text()) if path.exists() else {}
    latest = settings.data_dir / 'latest.json'
    if latest.exists():
        result = json.loads(latest.read_text())
        if result.get('plan', {}).get('city', '').casefold() == city.casefold() and result.get('run_id', '') > saved.get('run_id', ''):
            return result
    return saved


def run_city(city, settings, **kwargs):
    from agent.graph import run_pipeline
    result = run_pipeline(city_request(city), settings, **kwargs)
    path = settings.data_dir / 'runs' / result['run_id'] / 'result.json'
    saved = json.loads(path.read_text())
    saved['requested_city'] = city
    write_json(settings.data_dir / 'cities' / f'{city.lower()}.json', saved)
    return result


def run_all(settings):
    failed = []
    for city in CITIES:
        try:
            result = run_city(city, settings)
            print(f'{city}: {result["status"]}', flush=True)
            if result['status'] != 'success': failed.append(city)
        except Exception as error:
            # A setup failure for one city must not suppress the other cities.
            write_json(settings.data_dir / 'cities' / f'{city.lower()}.json',
                       {'status': 'failed', 'requested_city': city, 'errors': [str(error)]})
            failed.append(city)
            print(f'{city}: failed: {error}', flush=True)
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(run_all(Settings.from_env()))
