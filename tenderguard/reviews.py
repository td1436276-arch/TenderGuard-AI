from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


SCHEMA = """
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id TEXT NOT NULL,
    finding_id TEXT NOT NULL,
    status TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    note TEXT NOT NULL,
    reviewed_at TEXT NOT NULL
)
"""


def initialise_database(path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute(SCHEMA)
        connection.commit()


def save_reviews(path: str | Path, analysis_id: str, reviews: pd.DataFrame) -> int:
    initialise_database(path)
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = []
    for _, row in reviews.iterrows():
        status = str(row.get("Status", "Unreviewed"))
        note = str(row.get("Reviewer note", "")).strip()
        reviewer = str(row.get("Reviewer", "QS reviewer")).strip() or "QS reviewer"
        if status == "Unreviewed" and not note:
            continue
        rows.append((analysis_id, str(row["ID"]), status, reviewer, note, timestamp))
    if not rows:
        return 0
    with sqlite3.connect(path) as connection:
        connection.executemany(
            "INSERT INTO reviews (analysis_id, finding_id, status, reviewer, note, reviewed_at) VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        connection.commit()
    return len(rows)


def read_reviews(path: str | Path, analysis_id: str | None = None) -> pd.DataFrame:
    initialise_database(path)
    query = "SELECT analysis_id, finding_id, status, reviewer, note, reviewed_at FROM reviews"
    parameters: tuple[str, ...] = ()
    if analysis_id:
        query += " WHERE analysis_id = ?"
        parameters = (analysis_id,)
    query += " ORDER BY id DESC"
    with sqlite3.connect(path) as connection:
        return pd.read_sql_query(query, connection, params=parameters)

