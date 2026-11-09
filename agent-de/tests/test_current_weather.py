from unittest.mock import Mock
import pytest
from config import Settings
from pipeline.current_weather import answer_temperature


def test_temperature_alias_and_fresh_request():
    api = Mock()
    api.call_api.return_value = {'current': {'temperature_2m': 24.5, 'time': '2026-11-09T10:00'}, 'current_units': {'temperature_2m': '°C'}}
    result = answer_temperature('what is the temp in banglore?', Settings(), api=api)
    assert result['city'] == 'Bengaluru'
    assert result['temperature'] == 24.5
    assert api.call_api.call_args.kwargs['refresh'] is True
    with pytest.raises(ValueError):
        answer_temperature('temperature in unknown city', Settings(), api=api)


def test_rain_and_other_weather_details():
    api = Mock()
    api.call_api.return_value = {'current': {'temperature_2m': 21, 'time': '2026-11-09T10:00', 'rain': 0, 'showers': 1.2, 'weather_code': 80, 'relative_humidity_2m': 85}, 'current_units': {'temperature_2m': '°C'}}
    result = answer_temperature('Is it raining in Bangalore?', Settings(), api=api)
    assert 'Rain is indicated' in result['answer']
    assert result['current']['relative_humidity_2m'] == 85
    api.call_api.return_value['current']['showers'] = 0
    assert 'No rain is indicated' in answer_temperature('weather in Bengaluru', Settings(), api=api)['answer']
    with pytest.raises(ValueError, match='Forecast'):
        answer_temperature('weather in Bengaluru tomorrow', Settings(), api=api)


def test_sunny_day_night_and_clouds():
    api = Mock()
    current = {'temperature_2m': 25, 'time': '2026-11-09T12:00', 'weather_code': 0, 'is_day': 1}
    api.call_api.return_value = {'current': current, 'current_units': {'temperature_2m': '°C'}}
    assert answer_temperature('is it sunny in Bangalore?', Settings(), api=api)['answer'].startswith('Yes')
    current['is_day'] = 0
    assert 'nighttime' in answer_temperature('is it sunny in Bangalore?', Settings(), api=api)['answer']
    current.update(is_day=1, weather_code=2)
    assert 'sunny intervals' in answer_temperature('is it sunny in Bangalore?', Settings(), api=api)['answer']
    current['weather_code'] = 3
    assert 'does not indicate' in answer_temperature('is it sunny in Bangalore?', Settings(), api=api)['answer']
