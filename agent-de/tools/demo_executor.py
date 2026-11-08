"""Run repository-owned transformations on small free hosts without executing code."""
from itertools import product
from pipeline.contracts import transform_code, reference_frame
from tools.sql_tool import connection


def run_trusted_transform(code, *, settings, snapshots, plan, attempt_dir):
    if settings.provider != 'builtin':
        raise ValueError('Free demo mode supports only the built-in engine')
    options = next((dict(numeric=n, deduplicate=d, aliases=a)
                    for n, d, a in product((False, True), (False, True),
                                          ({}, {'temperature': 'temperature_2m'}))
                    if code == transform_code(numeric=n, deduplicate=d, aliases=a)), None)
    if options is None:
        raise ValueError('Demo mode accepts only trusted repository transformations')
    attempt_dir.mkdir(parents=True, exist_ok=True)
    path = attempt_dir / 'staging.duckdb'
    try:
        frame = reference_frame(snapshots, plan, options)
        with connection(path) as con:
            con.register('incoming', frame)
            con.execute('CREATE OR REPLACE TABLE staged AS SELECT * FROM incoming')
        return {'success': True, 'db_path': str(path), 'backend': 'trusted-demo',
                'stdout': f'Staged {len(frame)} hourly records using trusted transformation'}
    except Exception as error:
        return {'success': False, 'error': str(error), 'backend': 'trusted-demo'}
