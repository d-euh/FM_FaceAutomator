"""Opt-in local file protocol. A saved face and a game refresh are separate outcomes."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
import uuid

PROFILE = "fm27-steam-26620374-v1"


def bridge_root():
    if os.name != "nt" or not os.environ.get("LOCALAPPDATA"):
        return None
    return Path(os.environ["LOCALAPPDATA"]) / "FMFaceAutomator" / "live-refresh"


def read_json(file):
    if file.stat().st_size > 65536:
        raise ValueError("갱신 응답 파일이 너무 큽니다.")
    return json.loads(file.read_text(encoding="utf-8-sig"))


def write_json(file, value):
    file.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=file.parent, prefix=".request-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(value, output, ensure_ascii=False)
        os.replace(temporary, file)
    finally:
        Path(temporary).unlink(missing_ok=True)


def connection(root, now):
    sessions = []
    for path in sorted((root / "sessions").glob("*/status.json"))[-64:]:
        try:
            value = read_json(path)
            session = value.get("session", "")
            pid = value.get("pid")
            if (value.get("protocol") == 1 and value.get("profile") == PROFILE
                    and re.fullmatch(r"[a-f0-9]{32}", session) and type(pid) is int and pid > 0
                    and path.parent.name == f"{pid}-{session}"
                    and 0 <= now - float(value["heartbeat"]) <= 5):
                sessions.append((path.parent, value))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    if len(sessions) > 1:
        return None, "FM27 연결이 여러 개입니다. 사용할 게임 하나만 실행하세요."
    if not sessions:
        return None, "게임 갱신 플러그인 연결 대기 · 설치 후 FM27을 시작하세요."
    directory, session = sessions[0]
    if session.get("available") is not True:
        return (directory, session), "게임 갱신 불가 · " + str(session.get("reason", "연결 확인 필요"))
    return (directory, session), "게임 갱신 연결됨 · 실험 기능"


def pump(pending, root=None, now=None):
    """Return (new pending state, user-facing status). Never run AI or edit the pack."""
    now = time.time() if now is None else now
    root = bridge_root() if root is None else Path(root)
    if root is None:
        return pending, "게임 갱신은 Windows에서 사용할 수 있습니다."
    connected, status = connection(root, now)
    if not pending:
        return pending, status
    if not connected:
        return pending, status
    directory, session = connected
    if pending.get("request_id"):
        request_id = pending["request_id"]
        if not re.fullmatch(r"[a-f0-9]{32}", request_id):
            return None, "게임 갱신 요청 기록이 올바르지 않습니다."
        if pending.get("session") != session["session"]:
            # A new game process loaded the on-disk pack already; don't replay an uncertain old request.
            return None, "FM27이 다시 시작되어 이전 갱신 요청을 종료했습니다."
        reply = directory / "responses" / (request_id + ".json")
        if reply.is_file():
            value = read_json(reply)
            if (value.get("protocol"), value.get("id"), value.get("session"), value.get("profile")) != (1, request_id, session["session"], PROFILE):
                return pending, "게임 갱신 응답 확인 필요 · 요청 정보 불일치"
            result = value.get("status")
            if result == "refreshed":
                return None, "게임 그래픽 갱신 처리 완료 · 실제 얼굴 표시를 확인하세요."
            if result == "superseded":
                return None, "더 최신 페이스팩이 있어 이전 게임 갱신 요청을 종료했습니다."
            if result == "failed":
                return None, "게임 갱신 실패 · " + str(value.get("reason", "원인 확인 필요")) + " · 페이스온 파일 저장은 완료됨"
            return pending, "게임 갱신 응답 확인 필요 · 알 수 없는 결과"
        if now - pending.get("sent_at", now) > 260:
            return None, "게임 갱신 응답 시간 초과 · 자동 재요청하지 않습니다. 갱신 진단을 확인하세요."
        return pending, "게임 그래픽 갱신 대기 · " + str(session.get("reason") or session.get("stage", "게임 대기 중"))
    if session.get("available") is not True:
        return pending, status
    config = Path(pending["pack_dir"]) / "config.xml"
    if not config.is_file():
        return None, "게임 갱신 대상 config.xml이 없습니다."
    digest = hashlib.sha256(config.read_bytes()).hexdigest()
    request_id = uuid.uuid4().hex
    request = {"protocol": 1, "profile": PROFILE, "id": request_id, "session": session["session"],
               "pack_dir": str(config.parent.resolve()), "config_sha256": digest,
               "created_at": now, "expires_at": now + 180}
    write_json(root / "requests" / session["session"] / (request_id + ".json"), request)
    return pending | {"request_id": request_id, "session": session["session"], "sent_at": now}, "게임 그래픽 갱신 요청 · 게임이 대기 상태가 되면 처리합니다."
