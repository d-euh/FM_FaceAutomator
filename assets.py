"""Read-only discovery and ID mapping for existing FM facepacks and 2D kits."""
from __future__ import annotations

from collections import defaultdict
from io import BytesIO
import os
from pathlib import Path
import re
import random
import xml.etree.ElementTree as ET


EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
FACE = re.compile(r"graphics/pictures/person/(r-\d+|\d+)/portrait", re.I)
KIT = re.compile(r"graphics/pictures/team/(\d+)/kits/(home|away|third|goalkeeper(?:_(?:home|away|third))?|gk(?:_?(?:home|away|third|[123]))?|(?:home|away|third)_gk)", re.I)


def kit_variant(value):
    value = value.lower()
    if value in ("gk", "goalkeeper"):
        return "gk_home"
    if value.startswith("goalkeeper_"):
        return "gk_" + value.removeprefix("goalkeeper_")
    if value.endswith("_gk"):
        return "gk_" + value.removesuffix("_gk")
    if re.fullmatch(r"gk_?[123]", value):
        return "gk_" + {"1": "home", "2": "away", "3": "third"}[value[-1]]
    if value in ("gkhome", "gkaway", "gkthird"):
        return "gk_" + value[2:]
    return value


class AssetError(ValueError):
    def __init__(self, message, candidates=()):
        super().__init__(message)
        self.candidates = tuple(candidates)


class MissingFaceError(AssetError):
    def __init__(self, message, target):
        super().__init__(message)
        self.target = target


class MissingKitError(AssetError):
    """No usable kit path was found; different from a corrupt/configuration error."""


def _under(path, root):
    return path == root or path.is_relative_to(root)


def source_exclusions(config, folder):
    pack = Path(config["pack_dir"]).resolve()
    excluded = [config["state_dir"]]
    if not Path(folder).resolve().is_relative_to(pack) and (pack / ".fm-face-owner").exists() and not (pack / ".fm-face-shared").exists():
        excluded.append(str(pack))
    return excluded


def document_folders(home=None, environ=None):
    home = Path.home() if home is None else Path(home)
    environ = os.environ if environ is None else environ
    documents = [home / "Documents"]
    if os.name == "nt" and home == Path.home():
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as key:
                personal = winreg.QueryValueEx(key, "Personal")[0]
                documents.insert(0, Path(os.path.expandvars(personal)))
        except OSError:
            pass
    for key in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        if environ.get(key):
            documents.append(Path(environ[key]) / "Documents")
    return documents


def discover_roots(config, home=None, environ=None):
    """Candidate content directories only; never scan a whole drive or home."""
    documents = document_folders(home, environ)
    candidates = []
    for key in ("graphics_root", "portraits_dir", "kits_dir"):
        if config.get(key):
            candidates.append(Path(config[key]))
    source = config.get("source")
    if source and Path(source).parent.name.lower() == "games":
        candidates.append(Path(source).parent.parent / "graphics")
    for document in documents:
        for game in ("Football Manager 27", "Football Manager 2027"):
            candidates.append(document / "Sports Interactive" / game / "graphics")
    found = []
    excluded = [Path(config[k]).resolve() for k in ("state_dir", "pack_dir") if config.get(k)]
    for candidate in candidates:
        candidate = candidate.expanduser().resolve()
        if candidate.is_dir() and candidate not in found and not any(_under(candidate, e) for e in excluded):
            found.append(candidate)
    return [p for p in found if not any(p != other and _under(p, other) for other in found)]


class AssetCatalog:
    def __init__(self, root, exclude=(), stop=None, allow_managed=False):
        self.root = Path(root).expanduser().resolve()
        if not self.root.is_dir():
            raise AssetError(f"자료 폴더가 없습니다: {self.root}")
        self.exclude = [Path(p).resolve() for p in exclude if p]
        if any(_under(self.root, p) for p in self.exclude):
            raise AssetError("출력 페이스팩 또는 작업 폴더를 원본 자료로 사용할 수 없습니다.")
        self.faces = defaultdict(set)
        # FM26/27 pack precedence is later folder names first. Keep the config's
        # origin, because a mapped image can live in a differently named folder.
        self.face_mappings = {}
        self.face_conflicts = {}
        self.kits = defaultdict(set)
        self.direct = defaultdict(set)
        self.missing_faces = set()
        self.missing_kits = set()
        self.warnings = []
        self.textures = 0
        self.texture_paths = set()
        self.candidates = {}
        configs = []
        directories, files = 0, 0
        for folder, dirs, names in os.walk(self.root, followlinks=False, onerror=self._walk_error):
            if stop is not None and stop.is_set():
                raise AssetError("검색을 취소했습니다.")
            directories += 1
            if directories > 20000:
                raise AssetError("검색 폴더가 너무 큽니다. 개별 페이스팩/키트 폴더를 선택하세요.")
            base = Path(folder)
            managed = (base / ".fm-face-owner").is_file()
            shared = (base / ".fm-face-shared").is_file()
            if managed and not shared and not allow_managed:
                dirs[:] = []
                continue
            dirs[:] = sorted(d for d in dirs if not (base / d).is_symlink()
                             and not getattr(base / d, "is_junction", lambda: False)()
                             and not (d == ".fm-face-lock" or (d == "backups" and (managed or shared)))
                             and not any(_under((base / d).resolve(), e) for e in self.exclude))
            for name in sorted(names):
                files += 1
                if files > 1000000:
                    raise AssetError("검색 파일이 너무 많습니다. 검색 범위를 좁혀주세요.")
                path = base / name
                if path.is_symlink():
                    continue
                if name.lower() == "config.xml":
                    configs.append(path)
                elif path.suffix.lower() in EXTENSIONS:
                    stem = path.stem.lower()
                    direct = re.fullmatch(r"((?:r-)?\d+)(?:_(home|away|third|goalkeeper(?:_(?:home|away|third))?|gk(?:_?(?:home|away|third|[123]))?|(?:home|away|third)_gk))?", stem)
                    if direct:
                        key = direct.group(1) + ("_" + kit_variant(direct.group(2)) if direct.group(2) else "")
                        self.direct[key].add(path)
        for path in configs:
            if stop is not None and stop.is_set():
                raise AssetError("검색을 취소했습니다.")
            self._read_config(path)
        for stem in list(self.direct):
            self.direct[stem].difference_update(self.texture_paths)
            if not self.direct[stem]:
                del self.direct[stem]

    def _walk_error(self, error):
        self.warnings.append(f"폴더 읽기 실패: {error.filename}")

    def _folder_priority(self, folder):
        return tuple(part.casefold() for part in folder.relative_to(self.root).parts)

    def _record_face(self, target, path, priority):
        previous = self.face_mappings.get(target)
        if previous is None or priority > previous[0]:
            self.face_mappings[target] = (priority, path)
            self.face_conflicts.pop(target, None)
        elif priority == previous[0] and path != previous[1]:
            self.face_conflicts.setdefault(target, {previous[1]}).add(path)

    def _source(self, xml, source):
        if not str(source).strip():
            return None
        relative = Path(str(source).replace("\\", "/"))
        if relative.is_absolute() or re.match(r"^[A-Za-z]:", str(relative)):
            return None
        path = (xml.parent / relative).resolve()
        if not _under(path, self.root) or any(_under(path, e) for e in self.exclude):
            return None
        if path.is_file() and path.suffix.lower() in EXTENSIONS:
            return path
        for extension in EXTENSIONS:
            for suffix in (extension, extension.upper()):
                candidate = path.with_name(path.name + suffix)
                resolved = candidate.resolve()
                if candidate.is_file() and _under(resolved, self.root) and not any(_under(resolved, e) for e in self.exclude):
                    return resolved
        return None

    def _read_config(self, xml):
        try:
            if xml.stat().st_size > 64 * 1024 * 1024:
                raise ValueError("64MB를 넘는 config.xml")
            data = xml.read_bytes()
            # Graphics mappings never need a DTD or entities.
            if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
                raise ValueError("DTD/엔티티를 포함한 XML")
            records = []
            textures = 0
            texture_paths = set()
            # Don't publish a partially parsed malformed XML into the catalog.
            for _, element in ET.iterparse(BytesIO(data), events=("end",)):
                if element.tag == "record" and "to" in element.attrib:
                    target = element.get("to", "").replace("\\", "/").strip("/")
                    face, kit = FACE.fullmatch(target), KIT.fullmatch(target)
                    if "/kit_textures/" in target.lower():
                        textures += 1
                        texture = self._source(xml, element.get("from", ""))
                        if texture:
                            texture_paths.add(texture)
                    if face or kit:
                        path = self._source(xml, element.get("from", ""))
                        records.append((face.group(1).lower() if face else None,
                                        (kit.group(1), kit_variant(kit.group(2))) if kit else None, path))
                element.clear()
            self.textures += textures
            self.texture_paths.update(texture_paths)
            priority = self._folder_priority(xml.parent)
            for face, kit, path in records:
                if face:
                    self._record_face(face, path, priority)
                if path is None:
                    (self.missing_faces if face else self.missing_kits).add(face or kit)
                    continue
                (self.faces[face] if face else self.kits[kit]).add(path)
                parent = xml.parent if _under(path, xml.parent) else self.root
                group = self.candidates.setdefault(str(parent), {"path": str(parent), "faces": set(), "kits": set()})
                (group["faces"] if face else group["kits"]).add(face or kit)
        except (OSError, ValueError, ET.ParseError) as exc:
            self.warnings.append(f"{xml}: {exc}")

    @staticmethod
    def _choose(paths, description):
        paths = sorted({p for p in paths if p.is_file()})
        if len(paths) > 1:
            action = "‘유니폼 이미지 선택’에서 사용할 이미지를 선택하세요." if description.startswith("구단 ") else "사용할 개별 팩 폴더를 선택하세요."
            raise AssetError(f"{description}: 후보 {len(paths)}개가 겹칩니다. {action}", paths)
        if not paths:
            raise AssetError(f"{description}: 연결된 이미지 파일이 없습니다.")
        return paths[0]

    def face_target(self, player_id, regen=False):
        pid = str(player_id)
        key = ("r-" if regen else "") + pid
        # An existing r- mapping is positive evidence; never infer from ID size.
        regen_key = "r-" + pid
        regen_evidence = regen_key in self.faces or regen_key in self.missing_faces or (self.direct.get(regen_key) and not self.direct.get(pid))
        if not regen and pid not in self.missing_faces and not self.faces.get(pid) and regen_evidence:
            key = "r-" + pid
        return key

    def face(self, player_id, regen=False):
        pid = str(player_id)
        key = self.face_target(pid, regen)
        if key in self.face_mappings:
            if key in self.face_conflicts:
                paths = self.face_conflicts[key]
                raise AssetError(f"선수 {key}: 같은 팩의 config.xml에 서로 다른 사진 매핑이 겹칩니다. 해당 매핑을 확인하세요.", [p for p in paths if p is not None])
            _, path = self.face_mappings[key]
            if path is None or not path.is_file():
                raise MissingFaceError(f"선수 {key}: 우선순위가 높은 팩의 config.xml은 있지만 원본 이미지가 없습니다.", key)
            return path, key
        paths = self.direct.get(key, set()) or self.direct.get(pid, set())
        if not any(path.is_file() for path in paths):
            raise MissingFaceError(f"선수 {key}: 연결된 이미지 파일이 없습니다.", key)
        priority = max(self._folder_priority(path.parent) for path in paths if path.is_file())
        paths = [path for path in paths if self._folder_priority(path.parent) == priority]
        return self._choose(paths, f"선수 {key}"), key

    def kit(self, club_id, variant="home"):
        if variant not in ("home", "away", "third", "gk_home", "gk_away", "gk_third"):
            raise AssetError("유니폼 유형을 확인하세요.")
        key = (str(club_id), variant)
        if key in self.kits:
            return self._choose_kit(self.kits[key], f"구단 {club_id} {variant}")
        if key in self.missing_kits:
            raise MissingKitError(f"구단 {club_id} {variant}: config.xml은 있지만 키트 이미지가 없습니다.")
        paths = self.direct.get(f"{club_id}_{variant}", set())
        if not paths and variant == "home":
            paths = self.direct.get(str(club_id), set())
        return self._choose_kit(paths, f"구단 {club_id} {variant} 2D 키트")

    @staticmethod
    def _choose_kit(paths, description):
        available = sorted({p for p in paths if p.is_file()})
        if not available:
            raise MissingKitError(f"{description}: 연결된 이미지 파일이 없습니다.")
        return random.choice(available)

    def kit_candidates(self, club_id, variant="home"):
        """List all references for the optional manual preview, without choosing."""
        key = (str(club_id), variant)
        if key in self.kits:
            paths = self.kits[key]
        elif key in self.missing_kits:
            paths = ()
        else:
            paths = self.direct.get(f"{club_id}_{variant}", set())
            if not paths and variant == "home":
                paths = self.direct.get(str(club_id), set())
        return sorted(p for p in paths if p.is_file())

    def suggestions(self):
        found = [{"path": c["path"], "faces": len(c["faces"]), "kits": len(c["kits"]), "basis": "config.xml"}
                 for c in self.candidates.values()]
        if not found and self.direct:
            found.append({"path": str(self.root), "faces": 0, "kits": 0,
                          "basis": f"ID 파일 {sum(len(v) for v in self.direct.values())}개 · 종류 직접 확인"})
        return found


def reference_png(path):
    """Decode the chosen file only and stage its actual content as PNG."""
    from PIL import Image, ImageOps
    path = Path(path)
    if path.stat().st_size > 25 * 1024 * 1024:
        raise AssetError(f"참조 이미지가 25MB를 넘습니다: {path.name}")
    with Image.open(path) as image:
        if image.width > 8192 or image.height > 8192:
            raise AssetError("참조 이미지가 너무 큽니다. 8192px 이하의 이미지를 사용하세요.")
        image.load()
        staged = ImageOps.exif_transpose(image).convert("RGBA")
        out = BytesIO()
        staged.save(out, format="PNG")
        return out.getvalue()
