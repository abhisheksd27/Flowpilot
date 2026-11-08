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
