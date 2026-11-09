"""Forecast answers with explicit dates, units and issue time."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import re
import pandas as pd
from pipeline.cities import LOCATIONS
from pipeline.contracts import WEATHER
from tools.api_tool import APITool


def forecast(question, city, settings, *, api=None, today=None):
    loc = LOCATIONS[city]
    today = today or datetime.now(ZoneInfo(loc['timezone'])).date()
    start, end = today, today + timedelta(days=6)
    if re.search(r'tomorrow', question, re.I):
        start = end = today + timedelta(days=1)
    elif re.search(r'weekend', question, re.I):
        start = today + timedelta(days=(5 - today.weekday()) % 7) if today.weekday() != 6 else today
        end = start + timedelta(days=1 if start.weekday() == 5 else 0)
    elif re.search(r'next week', question, re.I):
        start = today + timedelta(days=7-today.weekday())
        end = start + timedelta(days=6)
    raw = (api or APITool(settings)).call_api(WEATHER, {
        'latitude': loc['latitude'], 'longitude': loc['longitude'], 'timezone': loc['timezone'],
        'forecast_days': 14, 'daily': 'temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,weather_code'}, refresh=True)
    frame = pd.DataFrame(raw['daily'])
    frame = frame[frame['time'].between(start.isoformat(), end.isoformat())]
    if frame.empty:
        raise ValueError('No forecast returned for the requested dates')
    return {'city': city, 'issued_at': datetime.now(ZoneInfo(loc['timezone'])).isoformat(),
            'units': raw.get('daily_units', {}), 'days': frame.to_dict('records'),
            'answer': '\n'.join(f"{r['time']}: rain probability {r['precipitation_probability_max']}%, low {r['temperature_2m_min']} °C, high {r['temperature_2m_max']} °C." for r in frame.to_dict('records'))}
