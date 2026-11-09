"""Replay archived inputs and simulate faults without touching the main warehouse."""
from copy import deepcopy
from dataclasses import replace
import json
from datetime import datetime, timezone
from pathlib import Path
from pipeline.contracts import WEATHER, AIR
from pipeline.operations import run_record
from tools.cache import digest


class SnapshotAPI:
    def __init__(self, snapshots):
        self.snapshots = snapshots
        self.metrics = {'requests': 0, 'cache_hits': 0, 'retries': 0}

    def call_api(self, url, params, *, refresh=False):
        if url not in (WEATHER, AIR):
            raise ValueError('Replay cannot request a new source')
        self.metrics['cache_hits'] += 1
        return deepcopy(self.snapshots['weather' if url == WEATHER else 'air'])


def archived_inputs(settings, run_id):
    run = run_record(settings, run_id)
    found = {}
    folder = settings.data_dir / 'bronze' / run_id
    for source in ('weather', 'air'):
        paths = sorted(folder.glob(f'attempt_*_{source}.json'), key=lambda p: int(p.name.split('_')[1]))
        if not paths:
            raise ValueError('Original input snapshots were not captured or have been retained elsewhere')
        raw = json.loads(paths[-1].read_text())
        if raw.get('sha256') != digest(raw['response']):
            raise ValueError('Snapshot hash verification failed')
        found[source] = raw['response']
    return run, found


def replay(settings, run_id):
    from agent.graph import run_pipeline
    run, snapshots = archived_inputs(settings, run_id)
    # Keep a separate warehouse so historical replay cannot overwrite current data.
    target = settings.data_dir / 'replays' / (run_id + '-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f'))
    selected = replace(settings, data_dir=target, provider='builtin', demo_mode=False)
    result = run_pipeline(run['user_request'], selected, api=SnapshotAPI(snapshots),
                          replay_plan=run['plan'], replay_code=run.get('code') or None)
    return result


class FaultAPI:
    """Corrupt only copies of real source responses in a dedicated simulation run."""
    def __init__(self, settings, scenario, persistent=False):
        from tools.api_tool import APITool
        self.api = APITool(settings)
        self.scenario, self.persistent, self.calls = scenario, persistent, 0
        self.metrics = self.api.metrics

    def call_api(self, url, params, *, refresh=False):
        raw = self.api.call_api(url, params, refresh=refresh)
        if url == WEATHER:
            self.calls += 1
            if self.persistent or self.calls == 1:
                if self.scenario == 'timeout':
                    raise TimeoutError('Deliberately injected weather timeout')
                raw = deepcopy(raw)
                if self.scenario == 'missing_field':
                    raw['hourly'].pop('relative_humidity_2m', None)
                elif self.scenario == 'null_value':
                    raw['hourly']['temperature_2m'][0] = None
                else:
                    raise ValueError('Unsupported fault scenario')
        return raw


def simulate(settings, city, scenario, persistent=False):
    from agent.graph import run_pipeline
    from pipeline.cities import city_request
    target = settings.data_dir / 'simulations' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    selected = replace(settings, data_dir=target, provider='builtin', demo_mode=False)
    # Establish a good baseline, then preserve it if the second run cannot recover.
    baseline = run_pipeline(city_request(city), selected, refresh=True)
    if baseline['status'] != 'success':
        raise ValueError('Could not establish a real validated simulation baseline')
    from tools.sql_tool import connection
    with connection(selected.db_path, read_only=True) as con:
        before = con.execute('SELECT time,location_id,temperature_c,humidity_pct,pm2_5_ug_m3 FROM silver_environment ORDER BY time').fetchdf()
    result = run_pipeline(city_request(city), selected, api=FaultAPI(selected, scenario, persistent), refresh=True)
    with connection(selected.db_path, read_only=True) as con:
        after = con.execute('SELECT time,location_id,temperature_c,humidity_pct,pm2_5_ug_m3 FROM silver_environment ORDER BY time').fetchdf()
    return {'baseline_rows': baseline['published']['warehouse_rows'], 'after_rows': len(after), 'result': result,
            'baseline_values_preserved': before.equals(after),
            'warehouse': str(selected.db_path), 'main_warehouse_untouched': True}
