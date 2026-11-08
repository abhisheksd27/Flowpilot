"""Supported Indian cities and independent city run records."""
import json
from config import Settings
from pipeline.events import write_json

CITIES = ('Bengaluru', 'Mumbai', 'Delhi', 'Chennai', 'Hyderabad', 'Kolkata')


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
