"""Export a read-only public dashboard from completed runs (no credentials or raw logs)."""
import ast
import json
from pathlib import Path
import shutil
from datetime import datetime, timezone
from config import ROOT, Settings
from pipeline.warehouse import preview


def export_site(settings: Settings, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    result = json.loads((settings.data_dir / 'latest.json').read_text())
    public = {key: result.get(key) for key in ('run_id', 'status', 'plan', 'code', 'validation_result', 'anomalies', 'published', 'retry_count')}
    public['events'] = [{k: e.get(k) for k in ('timestamp', 'node', 'status', 'message', 'retry_count')} for e in result.get('step_history', [])]
    public['generated_at'] = datetime.now(timezone.utc).isoformat()
    public['hourly'] = json.loads(preview(settings, 'silver_environment', 5000).to_json(orient='records', date_format='iso'))
    public['daily'] = json.loads(preview(settings, 'gold_daily_environment', 1000).to_json(orient='records', date_format='iso'))
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
