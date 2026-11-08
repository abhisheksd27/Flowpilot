"""Schema inspection and non-mutating source/target drift comparison."""
import json
from pathlib import Path
from typing import Any
from tools.sql_tool import connection, identifier


def inspect_schema(table: str, db_path: Path | None = None) -> dict:
    """Return types, total rows, and at most five example records."""
    from config import Settings
    path = db_path or Settings.from_env().db_path
    with connection(path, read_only=True) as con:
        name = identifier(table)
        columns = {row[0]: row[1] for row in con.execute(f"DESCRIBE {name}").fetchall()}
        return {"columns": columns,
                "row_count": con.execute(f"SELECT count(*) FROM {name}").fetchone()[0],
                "sample_rows": con.execute(f"SELECT * FROM {name} LIMIT 5").fetchdf().to_dict("records")}


def source_schema(snapshots: dict) -> dict:
    """Describe hourly fields without mistaking integers for type drift from floats."""
    def kind(values: Any) -> str:
        if not isinstance(values, list):
            return type(values).__name__
        present = [x for x in values if x is not None]
        if not present:
            return "unknown"
        if all(isinstance(x, (float, int)) and not isinstance(x, bool) for x in present):
            return "number"
        return "string" if all(isinstance(x, str) for x in present) else "mixed"
    return {f"{source}.{field}": kind(values) for source, payload in snapshots.items()
            for field, values in payload.get("hourly", {}).items()}


def compare_schema(expected: dict, incoming: dict) -> dict:
    """Return drift; possible rename pairs are hypotheses, not automatic mappings."""
    added = {k: v for k, v in incoming.items() if k not in expected}
    removed = {k: v for k, v in expected.items() if k not in incoming}
    changed = {k: {"before": expected[k], "after": v} for k, v in incoming.items()
               if k in expected and v != expected[k]}
    return {"added": added, "removed": removed, "type_changes": changed,
            "possible_renames": [{"from": old, "to": new} for old, typ in removed.items()
                                 for new, other in added.items() if typ == other],
            "detected": bool(added or removed or changed)}


def expected_schema(db_path: Path, dataset: str) -> dict:
    """Read the last accepted schema, never updating it during inspection."""
    if not db_path.exists():
        return {}
    with connection(db_path, read_only=True) as con:
        try:
            row = con.execute("SELECT schema_json FROM _agent_schemas WHERE dataset = ?", [dataset]).fetchone()
            return json.loads(row[0]) if row else {}
        except Exception:
            return {}
