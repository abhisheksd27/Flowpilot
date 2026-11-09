"""Bounded saved-data analytics; questions compile only to parameterized SELECTs."""
from datetime import datetime, timedelta
import re
import pandas as pd
from pipeline.cities import LOCATIONS
from tools.sql_tool import connection

METRIC_NAMES = {'temperature': 'temperature_c', 'humidity': 'humidity_pct', 'pm2.5': 'pm2_5_ug_m3'}


def records(settings, city, start, end, limit=100000):
    if start > end or (end - start).days > 366:
        raise ValueError('Choose an ordered date range of at most 366 days')
    loc = LOCATIONS[city]
    with connection(settings.db_path, read_only=True) as con:
        return con.execute("SELECT * FROM silver_environment WHERE location_id=? AND CAST(time AT TIME ZONE 'UTC' AT TIME ZONE ? AS DATE) BETWEEN ? AND ? ORDER BY time LIMIT ?",
                           [str(loc['id']), loc['timezone'], start, end, min(limit, 100000)]).fetchdf()


def history_comparison(settings, city):
    today = pd.Timestamp.now(tz=LOCATIONS[city]['timezone']).date()
    frame = records(settings, city, today - timedelta(days=1), today)
    if frame.empty:
        raise ValueError('No saved data for today or yesterday. Run this city first.')
    frame['date'] = pd.to_datetime(frame.time, utc=True).dt.tz_convert(LOCATIONS[city]['timezone']).dt.date
    daily = frame.groupby('date').agg(temperature_c=('temperature_c', 'mean'), hours=('time', 'nunique')).reset_index()
    if len(daily) != 2:
        raise ValueError('Both days are needed. Today may not have any completed hours yet.')
    delta = daily.iloc[1].temperature_c - daily.iloc[0].temperature_c
    return {'answer': f"Today's saved mean is {abs(delta):.2f} °C {'higher' if delta >= 0 else 'lower'} than yesterday. Partial-day means are not matched-hour comparisons.", 'days': daily}


def ask_saved(question, city, settings):
    if re.search(r'today.*(hotter|colder|warmer).*yesterday', question, re.I):
        return history_comparison(settings, city)
    match = re.fullmatch(r'\s*how many hours (?:exceeded|above) (-?\d+(?:\.\d+)?)\s*(?:°?c)?\s+(?:last week|in the last 7 days)\??\s*', question, re.I)
    if not match:
        raise ValueError('Supported: “How many hours exceeded 30°C last week?” or “Is today hotter than yesterday?”')
    today = pd.Timestamp.now(tz=LOCATIONS[city]['timezone']).date()
    start = today - timedelta(days=7)
    sql = "SELECT count(*) AS matching_hours, min(time) AS earliest, max(time) AS latest FROM silver_environment WHERE location_id=? AND temperature_c>? AND CAST(time AT TIME ZONE 'UTC' AT TIME ZONE ? AS DATE)>=? AND CAST(time AT TIME ZONE 'UTC' AT TIME ZONE ? AS DATE)<?"
    params = [str(LOCATIONS[city]['id']), float(match[1]), LOCATIONS[city]['timezone'], start, LOCATIONS[city]['timezone'], today]
    with connection(settings.db_path, read_only=True) as con:
        result = con.execute(sql, params).fetchdf()
    coverage = records(settings, city, start, today - timedelta(days=1))
    return {'answer': f"{result.iloc[0].matching_hours} saved hours exceeded {match[1]} °C. Coverage: {len(coverage)} of 168 expected hours; missing hours are not inferred.", 'sql': sql, 'params': params, 'days': result}


def explain_anomaly(settings, city, metric, timestamp):
    if metric not in METRIC_NAMES.values():
        raise ValueError('Unsupported measurement')
    from tools.anomaly_tool import detect_anomalies
    analysis = detect_anomalies('silver_environment', metric, settings.db_path, location_id=str(LOCATIONS[city]['id']))
    with connection(settings.db_path, read_only=True) as con:
        surrounding = con.execute('SELECT * FROM silver_environment WHERE location_id=? AND time BETWEEN ? AND ? ORDER BY time',
            [str(LOCATIONS[city]['id']), pd.Timestamp(timestamp) - pd.Timedelta(hours=3), pd.Timestamp(timestamp) + pd.Timedelta(hours=3)]).fetchdf()
    selected = [r for r in analysis.get('records', []) if pd.Timestamp(r['time']) == pd.Timestamp(timestamp)]
    return {'baseline_mean': analysis.get('mean'), 'baseline_std': analysis.get('std'), 'iqr_bounds': analysis.get('iqr_bounds'),
            'reason': selected or 'This timestamp is not flagged under the current full-history baseline.', 'surrounding': surrounding}
