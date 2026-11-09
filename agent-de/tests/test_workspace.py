from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
import json
import os
from unittest.mock import Mock
import pandas as pd
import pytest
from config import Settings
from agent.graph import run_pipeline
from pipeline.analytics import records, ask_saved, history_comparison, explain_anomaly
from pipeline.forecasts import forecast
from pipeline.operations import health, run_metrics, lineage, retention_candidates, apply_retention, daily_summary
from pipeline.rules import save_config, load_config
from pipeline.recovery import archived_inputs, SnapshotAPI
from tests.failure_injection.scenarios import ScenarioAPI, fixture_executor


@pytest.fixture
def populated(tmp_path):
    settings = Settings(data_dir=tmp_path, backoff_seconds=0)
    result = run_pipeline('weather for Bengaluru', settings, api=ScenarioAPI(), executor=fixture_executor)
    assert result['status'] == 'success'
    return settings, result


def test_analytics_health_lineage_and_summary(populated):
    settings, run = populated
    today = pd.Timestamp.now(tz='Asia/Kolkata').date()
    frame = records(settings, 'Bengaluru', today-timedelta(days=7), today)
    assert len(frame) > 0
    answer = ask_saved('How many hours exceeded 20°C last week?', 'Bengaluru', settings)
    assert 'saved hours exceeded' in answer['answer'] and '?' in answer['sql']
    with pytest.raises(ValueError):
        ask_saved('DROP TABLE silver_environment', 'Bengaluru', settings)
    assert health(settings)['last_success'] == run['run_id']
    assert not health(settings)['stale']
    assert len(lineage(settings, run['run_id'])['sources']) >= 2
    assert run_metrics(settings).iloc[0].rows > 0
    assert 'daily summary' in daily_summary(settings)
    assert 'surrounding' in explain_anomaly(settings, 'Bengaluru', 'temperature_c', frame.iloc[-1].time)


def test_custom_rules_block_publication(populated):
    settings, previous = populated
    config = {'city': 'Bengaluru', 'frequency': 'hourly', 'at': '08:00', 'measurements': ['temperature_c'],
              'rules': [{'metric': 'temperature_c', 'operator': 'above', 'threshold': 0, 'action': 'block'}]}
    save_config(settings, config)
    assert load_config(settings) == config
    failed = run_pipeline('weather for Bengaluru', settings, api=ScenarioAPI(), executor=fixture_executor)
    assert failed['status'] == 'failed' and not failed['published']
    assert failed['custom_rules'][0]['matches'] > 0
    assert health(settings)['last_success'] == previous['run_id']
    assert list((settings.data_dir / 'alerts').glob('failed-*.json'))


def test_incremental_and_historical_windows(populated):
    settings, previous = populated
    incremental = run_pipeline('weather for Bengaluru', settings, incremental=True, api=ScenarioAPI(), executor=fixture_executor)
    assert incremental['status'] == 'success', incremental['errors']
    assert incremental['published']['hourly_rows'] <= 3
    assert 'start_hour' in incremental['plan']['parameters']
    end = pd.Timestamp(previous['plan']['as_of']) - pd.Timedelta(days=2)
    start = end - pd.Timedelta(hours=23)
    backfill = run_pipeline('weather for Bengaluru', settings, window=(start, end), api=ScenarioAPI(), executor=fixture_executor)
    assert backfill['status'] == 'success', backfill['errors']
    assert backfill['published']['hourly_rows'] == 24
    assert any(c['check'] == 'historical_time_boundary' for c in backfill['validation_result']['checks'])
    invalid = run_pipeline('weather for Bengaluru', settings, window=(start, end+pd.Timedelta(days=100)), api=ScenarioAPI(), executor=fixture_executor)
    assert invalid['status'] == 'failed'


def test_snapshot_tampering_rejected(populated):
    settings, run = populated
    record, snapshots = archived_inputs(settings, run['run_id'])
    api = SnapshotAPI(snapshots)
    assert record['plan']['city'] == 'Bengaluru'
    path = sorted((settings.data_dir / 'bronze' / run['run_id']).glob('attempt_*weather.json'))[-1]
    doc = json.loads(path.read_text())
    doc['response']['hourly']['temperature_2m'][0] = 999
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match='hash'):
        archived_inputs(settings, run['run_id'])


def test_forecast_dates_and_units(tmp_path):
    api = Mock()
    api.call_api.return_value = {'daily': {'time': ['2026-11-10', '2026-11-14', '2026-11-15'],
        'temperature_2m_max': [30, 31, 29], 'temperature_2m_min': [20, 21, 22], 'precipitation_probability_max': [10, 80, 50],
        'precipitation_sum': [0, 4, 2], 'weather_code': [0, 61, 3]}, 'daily_units': {'precipitation_probability_max': '%'}}
    result = forecast('rain tomorrow', 'Bengaluru', Settings(data_dir=tmp_path), api=api, today=date(2026, 11, 9))
    assert len(result['days']) == 1 and '10%' in result['answer']
    weekend = forecast('this weekend', 'Bengaluru', Settings(data_dir=tmp_path), api=api, today=date(2026, 11, 9))
    assert len(weekend['days']) == 2


def test_retention_is_recoverable_and_protects_latest(populated):
    settings, run = populated
    old = settings.data_dir / 'reports' / 'old.md'
    old.write_text('old report')
    then = pd.Timestamp.now().timestamp()-200*86400
    os.utime(old, (then, then))
    protected = settings.data_dir / 'reports' / (run['run_id']+'.md')
    os.utime(protected, (then, then))
    assert old in retention_candidates(settings, 90) and protected not in retention_candidates(settings, 90)
    moved = apply_retention(settings, 90)
    assert len(moved) == 1 and Path(moved[0]).read_text() == 'old report'
    assert protected.exists() and settings.db_path.exists()


def test_solar_missing_values_and_bounded_rules(tmp_path):
    from pipeline.solar import fetch_solar
    settings = Settings(data_dir=tmp_path)
    settings.prepare()
    api = Mock()
    api.call_api.return_value = {'properties': {'parameter': {'ALLSKY_SFC_SW_DWN': {'20261001': 5.2, '20261002': -999}}}, 'header': {'fill_value': -999}, 'parameters': {'ALLSKY_SFC_SW_DWN': {'units': 'kW-hr/m^2/day'}}}
    solar = fetch_solar(settings, 'Bengaluru', date(2026,10,1), date(2026,10,2), api=api)
    assert solar['rows'][0]['available'] and solar['rows'][1]['solar_energy'] is None
    assert list((tmp_path/'sources').glob('*.json'))
    with pytest.raises(ValueError):
        save_config(settings, {'city':'Bengaluru','frequency':'hourly','measurements':['temperature_c'], 'rules':[{'metric':'temperature_c','operator':'above','threshold':float('nan'),'action':'block'}]})
