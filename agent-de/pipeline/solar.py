"""NASA POWER solar-energy context, stored separately from validated weather tables."""
from datetime import datetime, timezone
import math
from pipeline.cities import LOCATIONS
from pipeline.events import write_json
from tools.api_tool import APITool

URL = 'https://power.larc.nasa.gov/api/temporal/daily/point'


def fetch_solar(settings, city, start, end, *, api=None):
    if start > end or (end - start).days > 31:
        raise ValueError('Choose up to 31 days for solar context')
    if end >= datetime.now(timezone.utc).date():
        raise ValueError('Solar context requires completed historical dates')
    loc = LOCATIONS[city]
    raw = (api or APITool(settings)).call_api(URL, {
        'latitude': loc['latitude'], 'longitude': loc['longitude'], 'start': start.strftime('%Y%m%d'),
        'end': end.strftime('%Y%m%d'), 'parameters': 'ALLSKY_SFC_SW_DWN', 'community': 'RE', 'format': 'JSON'}, refresh=True)
    values = raw['properties']['parameter']['ALLSKY_SFC_SW_DWN']
    fill = raw.get('header', {}).get('fill_value', -999)
    rows = []
    for date, value in values.items():
        valid = isinstance(value, (int, float)) and value != fill and math.isfinite(value) and value >= 0
        rows.append({'date': datetime.strptime(date, '%Y%m%d').date().isoformat(), 'solar_energy': value if valid else None, 'available': valid})
    result = {'city': city, 'source': URL, 'retrieved_at': datetime.now(timezone.utc).isoformat(),
              'unit': raw.get('parameters', {}).get('ALLSKY_SFC_SW_DWN', {}).get('units', 'see NASA metadata'),
              'rows': rows, 'meaning': 'Daily solar radiation energy, not electricity demand or measured panel output. NASA local solar dates may differ from city civil dates.'}
    write_json(settings.data_dir / 'sources' / f'solar-{city}-{start}-{end}.json', result)
    return result
