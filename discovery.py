"""Populate first-run path defaults without confirmation dialogs."""
from __future__ import annotations

import os
from pathlib import Path
import shutil

from assets import AssetCatalog, discover_roots, document_folders, source_exclusions
from gunzo import name_font


def find_name_font():
    """Find a usable system font using the renderer's own validated defaults."""
    try:
        return str(Path(name_font()).resolve())
    except (OSError, ValueError):
        return ""


def find_codex(environ=None):
    environ = os.environ if environ is None else environ
    executable = shutil.which("codex")
    if executable and Path(executable).suffix.lower() not in (".cmd", ".bat"):
        return executable
    if environ.get("APPDATA"):
        npm = Path(environ["APPDATA"]) / "npm" / "node_modules" / "@openai"
        if npm.is_dir():
            matches = sorted(npm.rglob("codex.exe"))
            if matches:
                return str(matches[0])
    return ""


def discover_defaults(config, base, home=None, environ=None, stop=None):
    """Return only missing/default fields. Existing custom choices win."""
    base = Path(base).resolve()
    updates, notes = {}, []

    def unset(key, legacy=""):
        value = config.get(key, "")
        return not value or bool(legacy and Path(value).resolve() == (base / legacy).resolve())

    search = dict(config)
    if unset("name_font_path"):
        font = find_name_font()
        if font:
            updates["name_font_path"] = font
    if unset("source"):
        saves = []
        games = []
        for documents in document_folders(home, environ):
            for game in ("Football Manager 27", "Football Manager 2027"):
                games.append(documents / "Sports Interactive" / game / "games")
        if search.get("graphics_root"):
            root = Path(search["graphics_root"])
            games.append(root.parent / "games" if root.name.lower() == "graphics" else root / "games")
        for game in games:
            if not game.is_dir():
                continue
            for index, (folder, dirs, names) in enumerate(os.walk(game, followlinks=False)):
                if stop is not None and stop.is_set():
                    return {}, []
                dirs[:] = [d for d in dirs if not (Path(folder) / d).is_symlink()
                           and not getattr(Path(folder) / d, "is_junction", lambda: False)()]
                if index > 1000:
                    break
                for name in names:
                    path = Path(folder) / name
                    if path.suffix.lower() == ".fm" and not path.is_symlink():
                        try:
                            saves.append((path.stat().st_mtime_ns, str(path.resolve())))
                        except OSError:
                            pass
        if saves:
            updates["source"] = search["source"] = max(saves)[1]
    roots = discover_roots(search, home, environ)
    candidates = {}
    for root in roots:
        if stop is not None and stop.is_set():
            return {}, []
        try:
            catalog = AssetCatalog(root, exclude=source_exclusions(config, root), stop=stop,
                                   allow_managed=Path(root).resolve() == Path(config["pack_dir"]).resolve())
            for candidate in catalog.suggestions():
                candidates[candidate["path"]] = candidate
        except (OSError, ValueError) as exc:
            notes.append(str(exc))
    for key, kind, legacy in (("portraits_dir", "faces", "portraits"), ("kits_dir", "kits", "kits")):
        if not unset(key, legacy):
            continue
        matches = [item for item in candidates.values() if item[kind]]
        if matches:
            matches.sort(key=lambda item: (-item[kind], item["path"]))
            # Keep all leagues/kit packs in scope; duplicate kits are sampled.
            updates[key] = (os.path.commonpath([item["path"] for item in matches])
                            if kind == "kits" and len({Path(item["path"]).anchor for item in matches}) == 1
                            else matches[0]["path"])
    if unset("pack_dir", "facepack") and roots:
        source = Path(search["source"]) if search.get("source") else None
        adjacent = source.parent.parent / "graphics" if source and source.parent.name.lower() == "games" else None
        graphics = adjacent if adjacent and adjacent.is_dir() else next((p for p in roots if p.name.lower() == "graphics"), roots[0])
        updates["pack_dir"] = str(graphics / "000_FMFaceAutomator")
    if config.get("codex", "codex") == "codex":
        executable = find_codex(environ)
        if executable:
            updates["codex"] = executable
    return updates, notes
