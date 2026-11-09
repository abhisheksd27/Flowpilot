"""Health, durable alerts, metrics, lineage, daily summaries and recoverable retention."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import shutil
import pandas as pd
from pipeline.cities import LOCATIONS
from pipeline.events import write_json
from pipeline.warehouse import run_lock
from tools.sql_tool import connection


def load_runs(settings, limit=200):
    rows = []
    for path in sorted((settings.data_dir / 'runs').glob('*/result.json'), reverse=True)[:limit]:
        try:
            rows.append(json.loads(path.read_text()))
        except (ValueError, OSError):
            continue
    return rows


def run_record(settings, run_id):
    if not re.fullmatch(r'\d{8}T\d{6}_[a-f0-9]{8}', run_id):
        raise ValueError('Invalid run identifier')
    return json.loads((settings.data_dir / 'runs' / run_id / 'result.json').read_text())


def run_metrics(settings):
    rows = []
    for run in load_runs(settings):
        events = run.get('step_history', [])
        # Whole-run wall time, rather than summing nested operations twice.
        duration = (pd.Timestamp(events[-1]['timestamp']) - pd.Timestamp(events[0]['timestamp'])).total_seconds() if len(events) > 1 else None
        checks = run.get('validation_result', {}).get('checks', [])
        rows.append({'run_id': run['run_id'], 'city': run.get('plan', {}).get('city'), 'status': run['status'],
                     'seconds': duration, 'rows': run.get('published', {}).get('hourly_rows', 0),
                     'failed_checks': sum(not c['passed'] for c in checks),
                     'validation_failures': sum(e['node'] == 'validate' and e['status'] == 'failed' for e in events),
                     'missing_hours': next((c['detail'] for c in checks if c['check'] == 'hourly_coverage'), 'not checked'),
                     'duplicates': next((c['detail'] for c in checks if c['check'] == 'unique_business_keys'), 'not checked'),
                     'missing_count': next((int(re.match(r'\d+', c['detail'])[0]) for c in checks if c['check'] == 'hourly_coverage' and re.match(r'\d+', c['detail'])), None),
                     'duplicate_count': next((int(re.match(r'\d+', c['detail'])[0]) for c in checks if c['check'] == 'unique_business_keys' and re.match(r'\d+', c['detail'])), None),
                     'api_calls': run.get('metrics', {}).get('api', {}).get('requests', 0),
                     'cache_hits': run.get('metrics', {}).get('api', {}).get('cache_hits', 0),
                     'repairs': run.get('retry_count', 0), 'errors': '\n'.join(run.get('errors', []))})
    return pd.DataFrame(rows)


def health(settings, city='Bengaluru'):
    from pipeline.scheduler import scheduler_status
    runs = [r for r in load_runs(settings) if r.get('plan', {}).get('city') == city]
    success = next((r for r in runs if r['status'] == 'success'), None)
    latest = runs[0] if runs else None
    newest, age = None, None
    if settings.db_path.exists():
        try:
            with connection(settings.db_path, read_only=True) as con:
                newest = con.execute('SELECT max(time) FROM silver_environment WHERE location_id=?', [str(LOCATIONS[city]['id'])]).fetchone()[0]
            if newest:
                age = (datetime.now(timezone.utc) - newest.replace(tzinfo=timezone.utc)).total_seconds() / 3600
        except Exception:
            pass
    return {'city': city, 'last_success': success and success['run_id'], 'latest_run': latest and latest['run_id'],
            'latest_status': latest and latest['status'], 'latest_data_utc': str(newest) if newest else None,
            'age_hours': age, 'stale': age is None or age > 3,
            'errors': latest.get('errors', []) if latest else ['No run available'], 'scheduler': scheduler_status(settings)}


def alert(settings, key, message):
    path = settings.data_dir / 'alerts' / (key + '.json')
    if not path.exists():
        write_json(path, {'key': key, 'message': message, 'created_at': datetime.now(timezone.utc).isoformat()})


def check_alerts(settings, city='Bengaluru'):
    state = health(settings, city)
    if state['latest_status'] in ('failed', 'partial'):
        alert(settings, 'failed-' + state['latest_run'], '\n'.join(state['errors']) or 'Pipeline did not finish successfully')
    stale_path = settings.data_dir / 'alerts' / ('stale-' + city + '.json')
    if state['stale']:
        alert(settings, 'stale-' + city, f"{city} data is older than three hours or unavailable. Latest data: {state['latest_data_utc']}")
    elif stale_path.exists():
        stale_path.unlink()
    return state


def lineage(settings, run_id):
    run = run_record(settings, run_id)
    snapshots = []
    for path in sorted((settings.data_dir / 'bronze' / run_id).glob('*.json')):
        data = json.loads(path.read_text())
        snapshots.append({'file': str(path), **{k: data.get(k) for k in ('url', 'params', 'retrieved_at', 'sha256', 'cache_hit')}})
    return {'run_id': run_id, 'plan': run.get('plan'), 'code': run.get('code'),
            'validation': run.get('validation_result'), 'schema_drift': run.get('schema_drift'), 'sources': snapshots}


def daily_summary(settings, city='Bengaluru'):
    from pipeline.analytics import records
    today = pd.Timestamp.now(tz=LOCATIONS[city]['timezone']).date()
    yesterday = today - timedelta(days=1)
    frame = records(settings, city, yesterday, today)
    frame['date'] = pd.to_datetime(frame.time, utc=True).dt.tz_convert(LOCATIONS[city]['timezone']).dt.date
    daily = frame.groupby('date').agg(temperature=('temperature_c', 'mean'), humidity=('humidity_pct', 'mean'), pm25=('pm2_5_ug_m3', 'mean'), hours=('time', 'count'))
    metrics = run_metrics(settings)
    if not metrics.empty:
        metrics = metrics[metrics.city == city]
    text = f'# {city} daily summary — {today}\n\nGenerated {datetime.now(timezone.utc).isoformat()}. Local-day averages; partial days are labeled by their hour counts.\n\n'
    text += daily.to_string() + '\n\n'
    text += 'Recent pipeline runs (up to 200 retained results):\n' + (metrics.head(10).to_string(index=False) if not metrics.empty else 'No runs')
    path = settings.data_dir / 'summaries' / f'{today}-{city}.md'
    path.parent.mkdir(exist_ok=True)
    path.write_text(text)
    return text


def retention_candidates(settings, days):
    if not 7 <= days <= 3650:
        raise ValueError('Retention must be between 7 and 3650 days')
    cutoff = datetime.now().timestamp() - days * 86400
    protected = set()
    successful_cities = set()
    for run in load_runs(settings):
        city = run.get('plan', {}).get('city')
        if run['status'] == 'success' and city not in successful_cities:
            protected.add(run['run_id'])
            successful_cities.add(city)
    for path in [settings.data_dir / 'latest.json', *(settings.data_dir / 'cities').glob('*.json')]:
        if path.exists():
            try:
                protected.add(json.loads(path.read_text()).get('run_id'))
            except ValueError:
                pass
    candidates = []
    for folder in ('runs', 'bronze', 'reports', 'logs'):
        for path in (settings.data_dir / folder).glob('*'):
            if path.is_symlink() or path.name.startswith('.'):
                continue
            run_id = path.stem.removeprefix('run_') if path.is_file() else path.name
            if run_id not in protected and path.stat().st_mtime < cutoff:
                candidates.append(path)
    return candidates


def apply_retention(settings, days):
    # Recoverable move only, serialized against writers. Warehouse is never removed.
    with run_lock(settings):
        candidates = retention_candidates(settings, days)
        trash = settings.data_dir / 'retention-trash' / datetime.now().strftime('%Y%m%dT%H%M%S')
        moved = []
        for path in candidates:
            target = trash / path.relative_to(settings.data_dir)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(target))
            moved.append(str(target))
        return moved
