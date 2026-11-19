"""Choose persistent work records per save, retaining existing installations."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import sqlite3
import uuid


def source_key(source):
    return os.path.normcase(str(Path(source).resolve()))


def select_workspace(config, base, fresh=False):
    result = dict(config)
    if not result.get("source"):
        return result
    base = Path(base).resolve()
    key = source_key(result["source"])
    registry = dict(result.get("workspaces", {}))
    chosen = registry.get(key)
    if not chosen and not fresh:
        old = Path(result.get("state_dir", base / "state")).resolve()
        database = old / "queue.sqlite"
        if database.is_file():
            try:
                with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as db:
                    stored = db.execute("SELECT value FROM meta WHERE key='source'").fetchone()
                if stored and source_key(stored[0]) == key:
                    chosen = str(old)
            except sqlite3.Error:
                pass
    if not chosen or fresh:
        stem = re.sub(r"[^\w.-]+", "_", Path(result["source"]).stem)[:45] or "save"
        digest = hashlib.sha256(key.encode()).hexdigest()[:12]
        suffix = "-" + uuid.uuid4().hex[:8] if fresh else ""
        chosen = str(base / "workspaces" / f"{stem}-{digest}{suffix}")
    registry[key] = chosen
    result.update(state_dir=chosen, workspaces=registry)
    return result
