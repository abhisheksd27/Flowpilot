"""Statistical anomaly inspection with explicit degenerate-baseline handling."""
from pathlib import Path
import numpy as np
import pandas as pd
from tools.sql_tool import connection, identifier


def detect_anomalies(table: str, column: str, db_path: Path | None = None,
                     *, location_id: str | None = None) -> dict:
    """Flag |z| > 3 and 1.5-IQR outliers, using population standard deviation."""
    from config import Settings
    with connection(db_path or Settings.from_env().db_path, read_only=True) as con:
        query = f"SELECT * FROM {identifier(table)}"
        frame = con.execute(query + (" WHERE location_id=?" if location_id else ""),
                            [location_id] if location_id else []).fetchdf()
    if column not in frame or not pd.api.types.is_numeric_dtype(frame[column]):
        return {"status": "nonnumeric", "column": column, "records": [], "count": 0}
    frame = frame[np.isfinite(frame[column])].copy()
    values = frame[column].astype(float)
    if len(values) < 8:
        return {"status": "insufficient_data", "column": column, "samples": len(values), "records": [], "count": 0}
    std = float(values.std(ddof=0))
    q1, q3 = values.quantile([0.25, 0.75])
    iqr = float(q3 - q1)
    frame["z_score"] = (values - values.mean()) / std if std > 0 else 0.0
    frame["z_flag"] = frame["z_score"].abs() > 3
    frame["iqr_flag"] = ((values < q1 - 1.5 * iqr) | (values > q3 + 1.5 * iqr)) if iqr > 0 else False
    flagged = frame[frame["z_flag"] | frame["iqr_flag"]]
    keys = [c for c in ("time", "date", "city", column, "z_score", "z_flag", "iqr_flag") if c in flagged]
    return {"status": "ok" if std and iqr else "degenerate_baseline", "column": column,
            "samples": len(values), "count": len(flagged), "mean": float(values.mean()), "std": std,
            "iqr_bounds": [float(q1 - 1.5 * iqr), float(q3 + 1.5 * iqr)],
            "records": flagged[keys].to_dict("records"),
            "limitations": "Statistical outliers in modeled data; not confirmed incidents. Hourly seasonality is not removed."}
