"""Populate first-run path defaults without confirmation dialogs."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

from assets import FACE, KIT, discover_roots, document_folders, source_exclusions


def sample_pack(xml, stop=None):
    """Classify a folder from at most 256 KiB of XML, without resolving images.

    This is a path suggestion, not validation of the pack. AssetCatalog still
    validates the complete mappings when the user actually uses the assets.
    """
    parser = ET.XMLPullParser(events=('end',))
    counts = {'faces': 0, 'kits': 0}
    tail = b''
    with xml.open('rb') as stream:
        for _ in range(4):
            if stop is not None and stop.is_set():
                return counts
            data = stream.read(65536)
            if not data:
                parser.close()
                break
            checked = (tail + data).upper()
            if b'<!DOCTYPE' in checked or b'<!ENTITY' in checked:
                raise ValueError('DTD/엔티티를 포함한 XML')
            tail = data[-16:]
            parser.feed(data)
            for _, element in parser.read_events():
                if element.tag == 'record':
                    target = element.get('to', '').replace('\\', '/').strip('/')
                    if FACE.fullmatch(target):
                        counts['faces'] += 1
                    elif KIT.fullmatch(target):
                        counts['kits'] += 1
                element.clear()
    return counts


def discover_packs(root, excluded, notes, stop=None):
    """Walk directories using cached DirEntry metadata; never stat each image."""
    pending = [Path(root)]
    excluded = [Path(path).resolve() for path in excluded]
    visited = 0
    while pending:
        if stop is not None and stop.is_set():
            return
        folder = pending.pop()
        visited += 1
        if visited > 10000:
            notes.append(f'{root}: 검색 폴더가 너무 많습니다. 자료 검색 위치를 좁혀주세요.')
            return
        if any(folder.is_relative_to(path) for path in excluded):
            continue
        if (folder / '.fm-face-owner').exists() and not (folder / '.fm-face-shared').exists():
            continue
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    if stop is not None and stop.is_set():
                        return
                    if entry.is_symlink() or getattr(entry, 'is_junction', lambda: False)():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name != '.fm-face-lock':
                            pending.append(Path(entry.path))
                    elif entry.name.lower() == 'config.xml' and entry.is_file(follow_symlinks=False):
                        try:
                            counts = sample_pack(Path(entry.path), stop)
                            if any(counts.values()):
                                yield {'path': str(folder), **counts}
                        except (OSError, ValueError, ET.ParseError) as exc:
                            notes.append(f'{entry.path}: {exc}')
        except OSError as exc:
            notes.append(f'{folder}: {exc}')


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
    if stop is not None and stop.is_set():
        return {}, []
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
    needs_packs = unset('portraits_dir', 'portraits') or unset('kits_dir', 'kits')
    needs_output = unset('pack_dir', 'facepack')
    roots = discover_roots(search, home, environ) if needs_packs or needs_output else []
    candidates = {}
    for root in roots if needs_packs else ():
        if stop is not None and stop.is_set():
            return {}, []
        try:
            for candidate in discover_packs(root, source_exclusions(config, root), notes, stop):
                candidates[candidate["path"]] = candidate
        except (OSError, ValueError) as exc:
            notes.append(str(exc))
    for key, kind, legacy in (("portraits_dir", "faces", "portraits"), ("kits_dir", "kits", "kits")):
        if not unset(key, legacy):
            continue
        matches = [item for item in candidates.values() if item[kind]]
        if matches:
            matches.sort(key=lambda item: (-item[kind], item["path"]))
            # A bounded XML sample cannot rank full pack sizes. Include the
            # discovered packs under a common root rather than dropping an
            # existing face reference because another sample had more records.
            updates[key] = (os.path.commonpath([item["path"] for item in matches])
                            if len({Path(item["path"]).anchor for item in matches}) == 1
                            else matches[0]["path"])
    if needs_output and roots:
        source = Path(search["source"]) if search.get("source") else None
        adjacent = source.parent.parent / "graphics" if source and source.parent.name.lower() == "games" else None
        graphics = adjacent if adjacent and adjacent.is_dir() else next((p for p in roots if p.name.lower() == "graphics"), roots[0])
        updates["pack_dir"] = str(graphics / "000_FMFaceAutomator")
    if stop is not None and stop.is_set():
        return {}, []
    if config.get("codex", "codex") == "codex":
        executable = find_codex(environ)
        if executable:
            updates["codex"] = executable
    return updates, notes
