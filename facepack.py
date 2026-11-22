"""Update one portrait in an existing FM pack while preserving unrelated XML."""
from __future__ import annotations

import json
from pathlib import Path
import re
import uuid
import xml.etree.ElementTree as ET


def document(data=None):
    if data is None:
        root = ET.Element("record")
        ET.SubElement(root, "boolean", id="preload", value="false")
        ET.SubElement(root, "boolean", id="amap", value="false")
    else:
        if len(data) > 64 * 1024 * 1024 or b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
            raise ValueError("페이스팩 config.xml의 크기 또는 DTD/엔티티를 확인하세요.")
        root = ET.fromstring(data, parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True)))
        if root.tag != "record":
            raise ValueError("페이스팩 config.xml의 루트는 record여야 합니다.")
    lists = root.findall("./list")
    matches = [item for item in lists if item.get("id") == "maps"]
    if not matches:
        matches = [item for item in lists if not item.get("id")]
    if len(matches) > 1:
        raise ValueError("페이스팩 config.xml의 매핑 목록이 여러 개입니다.")
    maps = matches[0] if matches else ET.SubElement(root, "list", id="maps")
    return root, maps


def load(pack):
    config = Path(pack) / "config.xml"
    data = config.read_bytes() if config.exists() else None
    root, maps = document(data)
    return data, root, maps


def person_id(record):
    if record.tag != "record":
        return None
    target = record.get("to", "").replace("\\", "/").strip("/")
    match = re.fullmatch(r"graphics/pictures/person/(?:r-)?(\d+)/portrait", target, re.I)
    return match.group(1) if match else None


def check_destination(pack, maps, player_id):
    destination = (Path(pack) / (player_id + ".png")).resolve()
    for record in maps:
        if record.tag != "record" or person_id(record) == player_id:
            continue
        source = record.get("from", "").replace("\\", "/")
        if not source:
            continue
        path = Path(pack) / source
        # FM config usually omits the extension; keep all existing source names.
        candidates = [path, path.with_name(path.name + ".png")]
        if any(path.resolve() == destination for path in candidates):
            raise ValueError(f"{player_id}.png가 다른 매핑에서도 사용됩니다. 해당 파일 연결을 먼저 확인하세요.")


def snapshot(pack, player_id, label, write, data):
    pack = Path(pack)
    backup = pack / "backups" / f"{label}-{uuid.uuid4().hex}.xml"
    filename = player_id + ".png"
    original = pack / filename
    exists = original.is_file()
    if exists:
        write(backup.with_suffix(".images") / filename, original.read_bytes())
    # Backup XML is exact original bytes. A missing config has an empty snapshot.
    write(backup, data if data is not None else ET.tostring(document()[0], encoding="utf-8"))
    write(backup.with_suffix(".json"), json.dumps({"version": 2, "player_id": player_id,
          "image_existed": exists, "config_existed": data is not None}).encode("utf-8"))
    return backup


def replace_portrait(pack, player_id, image, xml, before_xml, backup, write):
    output, config = pack / (player_id + '.png'), pack / 'config.xml'
    before_image = backup.with_suffix('.images') / output.name
    previous = before_image.read_bytes() if before_image.exists() else None
    try:
        if image is None:
            output.unlink(missing_ok=True)
        else:
            write(output, image)
        write(config, xml)
    except Exception as exc:
        errors = []
        for file, data in ((output, previous), (config, before_xml)):
            try:
                current = file.read_bytes() if file.exists() else None
                if current != data:
                    if data is None:
                        file.unlink(missing_ok=True)
                    else:
                        write(file, data)
            except Exception as error:
                errors.append(str(error))
        if errors:
            raise OSError(f'저장 실패 후 일부 파일을 복원하지 못했습니다. 백업: {backup}') from exc
        raise


def apply(pack, player_id, target_id, artifact, label, write):
    pack = Path(pack)
    data, root, maps = load(pack)
    check_destination(pack, maps, player_id)
    backup = snapshot(pack, player_id, label, write, data)
    for record in list(maps):
        if person_id(record) == player_id:
            maps.remove(record)
    ET.SubElement(maps, "record", {"from": player_id, "to": f"graphics/pictures/person/{target_id}/portrait"})
    replace_portrait(pack, player_id, Path(artifact).read_bytes(),
                     ET.tostring(root, encoding='utf-8', xml_declaration=True), data, backup, write)
    return backup


def restore(pack, backup, write):
    pack, backup = Path(pack), Path(backup)
    meta = json.loads(backup.with_suffix(".json").read_text(encoding="utf-8"))
    player_id = meta.get("player_id", "")
    if meta.get("version") != 2 or not isinstance(player_id, str) or not re.fullmatch(r"\d+", player_id):
        raise ValueError("페이스팩 백업 정보가 올바르지 않습니다.")
    old_root, old_maps = document(backup.read_bytes())
    records = [(index, record) for index, record in enumerate(old_maps) if person_id(record) == player_id]
    del old_root, old_maps
    data, root, maps = load(pack)
    check_destination(pack, maps, player_id)
    original = backup.with_suffix(".images") / (player_id + ".png")
    if meta["image_existed"] and not original.is_file():
        raise ValueError("복구할 원본 이미지 백업이 없습니다.")
    before = snapshot(pack, player_id, "before-restore", write, data)
    for record in list(maps):
        if person_id(record) == player_id:
            maps.remove(record)
    for index, record in records:
        maps.insert(min(index, len(maps)), record)
    image = original.read_bytes() if meta['image_existed'] else None
    replace_portrait(pack, player_id, image,
                     ET.tostring(root, encoding='utf-8', xml_declaration=True), data, before, write)
