"""Read-only player search against the latest successfully parsed save snapshot."""
from __future__ import annotations

from pathlib import Path
import sqlite3
from contextlib import closing


def find_players(database, query="", selected_ids=(), limit=150):
    database = Path(database)
    if not database.is_file():
        return [], []
    columns = "id,json_extract(data,'$.name') AS name,json_extract(data,'$.english_name') AS english_name,json_extract(data,'$.club_name') AS club_name"
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)) as db:
        db.row_factory = sqlite3.Row
        db.create_function("casefold", 1, lambda text: str(text or "").casefold())
        query = query.strip().casefold()
        rows = db.execute(f"SELECT {columns} FROM people WHERE ?='' OR id=? OR instr(casefold(json_extract(data,'$.name') || ' ' || COALESCE(json_extract(data,'$.english_name'),'') || ' ' || COALESCE(json_extract(data,'$.club_name'),'')),?)>0 ORDER BY casefold(json_extract(data,'$.name')),id LIMIT ?", (query, query, query, min(150, max(1, limit)))).fetchall()
        chosen = []
        ids = sorted({str(pid) for pid in selected_ids if str(pid).isdigit()})
        for start in range(0, len(ids), 400):
            chunk = ids[start:start + 400]
            placeholders = ",".join("?" for _ in chunk)
            chosen.extend(db.execute(f"SELECT {columns} FROM people WHERE id IN ({placeholders})", chunk).fetchall())
    return [dict(row) for row in rows], [dict(row) for row in chosen]
