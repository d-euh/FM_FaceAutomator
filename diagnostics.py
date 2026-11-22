"""One read-only diagnostic bundle for queue failures and live game refreshes."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from live_refresh import bridge_root, read_json

APP_VERSION = "0.17.0"


def squad_record(data):
    """Export registration evidence without prompts, names or image paths."""
    row = json.loads(data)
    if not isinstance(row, dict):
        raise ValueError("invalid player record")
    fields = ("club_id", "registered_club_id", "registered_team_id", "club_basis",
              "from_club_id", "from_team_id", "from_registered_club_id",
              "last_club_id", "last_registered_team_id", "last_registered_club_id", "game_wait")
    result = {key: row[key] for key in fields if key in row}
    history = row.get("last_squad_registration")
    if isinstance(history, dict):
        result["last_squad_registration"] = {key: history[key] for key in ("club_id", "team_id") if key in history}
    evidence = row.get("squad_evidence")
    if isinstance(evidence, dict):
        result["squad_evidence"] = {}
        for side in ("incoming", "outgoing"):
            value = evidence.get(side)
            if isinstance(value, dict):
                result["squad_evidence"][side] = {
                    key: value[key] for key in ("kind", "reason", "native_team_index", "team_unique_id", "club_id")
                    if key in value}
    return result


def recent_files(directory, pattern, limit):
    files = []
    for path in directory.glob(pattern):
        try:
            files.append((path.stat().st_mtime, path))
        except OSError:
            continue
    return [path for _, path in sorted(files, reverse=True)[:limit]]


def export_bundle(destination, *, config_path=None, config=None, root=None, bridge=None):
    """Never open Engine or read a save, prompt, image, or Codex credentials."""
    from engine import load_config, write_atomic
    root = Path(root) if root else Path(__file__).resolve().parent
    report = {"schema_version": 3, "kind": "fm_face_diagnostic_bundle", "app_version": APP_VERSION,
              "exported_at_utc": datetime.now(timezone.utc).isoformat(), "sessions": [], "jobs": [], "errors": []}
    bridge = Path(bridge) if bridge is not None else bridge_root()
    if bridge:
        for file in recent_files(bridge / "sessions", "*/status.json", 5):
            session = {"responses": []}
            report["sessions"].append(session)
            try:
                session["status"] = read_json(file)
            except (OSError, ValueError) as exc:
                session["status_error"] = type(exc).__name__
            for response in recent_files(file.parent / "responses", "*.json", 10):
                try:
                    session["responses"].append(read_json(response))
                except (OSError, ValueError) as exc:
                    session["responses"].append({"read_error": type(exc).__name__})
    if not report["sessions"]:
        report["errors"].append("live_plugin_session_not_found")
    if config is None:
        try:
            config = load_config(config_path or root / "config.json")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            report["errors"].append("config:" + type(exc).__name__)
    if config is not None:
        report["settings"] = {key: config.get(key) for key in ("source", "state_dir", "pack_dir", "live_refresh_enabled")}
        scope = config.get("scope_rules")
        if isinstance(scope, dict):
            report["settings"]["scope_rules"] = {
                key: scope[key] for key in ("preset", "direction", "clubs", "include_managed", "squad_types")
                if key in scope}
        database = Path(config["state_dir"]) / "queue.sqlite"
        if database.is_file():
            try:
                with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=2) as db:
                    db.row_factory = sqlite3.Row
                    report["workspace"] = dict(db.execute("SELECT key,value FROM meta WHERE key IN ('live_refresh_pending','live_refresh_status','live_refresh_session','live_refresh_last_result','source_stamp','detection_summary')"))
                    for job in db.execute("SELECT id,player_id,data,status,note,created,started,artifact FROM jobs ORDER BY id DESC LIMIT 30"):
                        item = {key: job[key] for key in ("id", "player_id", "status", "note", "created", "started")}
                        try:
                            item["squad_event"] = squad_record(job["data"])
                            person = db.execute("SELECT data FROM people WHERE id=?", (job["player_id"],)).fetchone()
                            if person:
                                item["squad_current"] = squad_record(person["data"])
                                event_identity = json.loads(job["data"]).get("identity")
                                item["same_identity"] = bool(event_identity and event_identity == json.loads(person["data"]).get("identity"))
                        except (ValueError, TypeError) as exc:
                            item["squad_error"] = type(exc).__name__
                        item["artifact_exists"] = bool(job["artifact"] and Path(job["artifact"]).is_file())
                        custom = db.execute("SELECT options,editing FROM job_custom WHERE job_id=?", (job["id"],)).fetchone()
                        item["has_custom"] = bool(custom and custom["options"] != "{}")
                        item["editing"] = bool(custom and custom["editing"])
                        item["retained_outputs"] = []
                        for folder in recent_files(database.parent / "jobs", f"{job['id']}-*", 3):
                            if folder.is_symlink() or not folder.is_dir():
                                continue
                            output = {"folder": folder.name, "portrait_exists": (folder / "portrait.png").is_file(),
                                      "result_exists": (folder / "result.png").is_file()}
                            try:
                                output["reply_status"] = read_json(folder / "reply.json").get("status")
                            except (OSError, ValueError, AttributeError) as exc:
                                output["reply_error"] = type(exc).__name__
                            item["retained_outputs"].append(output)
                        report["jobs"].append(item)
            except (sqlite3.Error, OSError) as exc:
                report["errors"].append("queue:" + type(exc).__name__)
        else:
            report["errors"].append("queue_not_found")
    try:
        record = json.loads((root / ".refresh-diagnostics.json").read_text(encoding="utf-8-sig"))
        source = Path(record["game"]) / "BepInEx" / "diagnostics" / "FMFaceRefresh" / "refresh-diagnostic.json"
        if source.stat().st_size > 10 * 1024 * 1024:
            raise ValueError("metadata too large")
        metadata = json.loads(source.read_text(encoding="utf-8-sig"))
        report["metadata"] = {key: value for key, value in metadata.items() if key != "candidate_assemblies"}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        report["errors"].append("static_metadata:" + type(exc).__name__)
    destination = Path(destination)
    write_atomic(destination, json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8"))
    return destination
