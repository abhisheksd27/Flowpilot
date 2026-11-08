import json
import pytest
from config import Settings
from pipeline.cities import city_result, run_city
from pipeline.export_site import export_site
from pipeline.contracts import GEO
from tests.failure_injection.scenarios import ScenarioAPI, fixture_executor


class CityAPI(ScenarioAPI):
    def call_api(self, url, params, **kwargs):
        response = super().call_api(url, params, **kwargs)
        if url == GEO:
            raise AssertionError('Catalog cities must not need a live geocoding lookup')
        return response


def test_city_isolation_and_export(tmp_path):
    settings = Settings(data_dir=tmp_path/'data', backoff_seconds=0)
    for city in ('Bengaluru', 'Mumbai'):
        result = run_city(city, settings, api=CityAPI(), executor=fixture_executor)
        assert result['status'] == 'success'
        assert result['plan']['country'] == 'India'
    assert city_result(settings, 'Bengaluru')['plan']['city'] == 'Bengaluru'
    assert city_result(settings, 'Mumbai')['plan']['city'] == 'Mumbai'
    assert city_result(settings, 'Delhi') == {}
    out = tmp_path/'site'
    export_site(settings, out)
    snapshot = json.loads((out/'snapshot.json').read_text())
    for city in ('Bengaluru', 'Mumbai'):
        item = snapshot['cities'][city]
        assert item['status'] == 'success'
        assert item['hourly'] and item['daily']
        assert {row['city'] for row in item['hourly']} == {city}
        assert {row['city'] for row in item['daily']} == {city}
    assert snapshot['cities']['Delhi']['status'] == 'not_started'
    assert snapshot['cities']['Delhi']['hourly'] == []
    with pytest.raises(ValueError):
        city_result(settings, '../other')
