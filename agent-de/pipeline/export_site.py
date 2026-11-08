"""Export a read-only public dashboard from completed runs (no credentials or raw logs)."""
import ast
import json
from pathlib import Path
import shutil
from datetime import datetime, timezone
from config import ROOT, Settings
from pipeline.warehouse import preview
from pipeline.cities import CITIES, city_result
from tools.sql_tool import connection


def export_site(settings: Settings, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc).isoformat()
    cities = {}
    for city in CITIES:
        result = city_result(settings, city)
        item = {key: result.get(key) for key in ('run_id', 'status', 'plan', 'code', 'validation_result', 'anomalies', 'published', 'retry_count')}
        item['city'] = city
        item['status'] = item['status'] or 'not_started'
        item['events'] = [{k: e.get(k) for k in ('timestamp', 'node', 'status', 'message', 'retry_count')} for e in result.get('step_history', [])]
        item['generated_at'] = generated
        item['hourly'], item['daily'] = [], []
        location = (result.get('plan') or {}).get('location_id')
        if location and settings.db_path.exists():
            with connection(settings.db_path, read_only=True) as con:
                for key, table, order, limit in [('hourly', 'silver_environment', 'time', 5000), ('daily', 'gold_daily_environment', 'date', 1000)]:
                    exists = con.execute('SELECT count(*) FROM information_schema.tables WHERE table_name=?', [table]).fetchone()[0]
                    if exists:
                        frame = con.execute(f'SELECT * FROM {table} WHERE location_id=? ORDER BY {order} DESC LIMIT ?', [location, limit]).fetchdf()
                        item[key] = json.loads(frame.to_json(orient='records', date_format='iso'))
        cities[city] = item
    public = dict(cities['Bengaluru'])
    public['cities'] = cities
    # Reuse the exact locally bundled architecture renderer and CSS, without importing Streamlit.
    tree = ast.parse((ROOT / 'ui_flow.py').read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id == 'NODES':
                public['nodeIds'] = {k: v[0] for k, v in ast.literal_eval(node.value).items()}
    shutil.copy2(ROOT / 'ui_assets/flow.css', output / 'flow.css')
    public['diagram'] = (ROOT / 'docs/architecture.mmd').read_text()
    (output / 'snapshot.json').write_text(json.dumps(public, default=str, allow_nan=False))
    for name in ('flow.bundle.js', 'flow.bundle.js.LEGAL.txt'):
        path = ROOT / 'ui_assets' / name
        if path.exists(): shutil.copy2(path, output / name)
    for path in (ROOT / 'web').iterdir():
        if path.is_file() and not path.name.startswith('.'):
            shutil.copy2(path, output / path.name)
    # Published warehouse is the durable checkpoint for the next cloud run.
    shutil.copy2(settings.db_path, output / 'pipeline.duckdb')
    (output / '.nojekyll').touch()


if __name__ == '__main__':
    import sys
    export_site(Settings.from_env(), Path(sys.argv[1] if len(sys.argv) > 1 else 'site'))
