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
MIN_PLUGIN_VERSION = (0, 2, 3)


def plugin_is_current(session):
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", str(session.get("plugin_version", "")))
    return bool(match and tuple(map(int, match.groups())) >= MIN_PLUGIN_VERSION)


def wait_description(session):
    reason = str(session.get("reason", ""))
    stage = session.get("stage")
    if not plugin_is_current(session):
        return "갱신 플러그인 업데이트 필요 · FM27 종료 후 install_live_refresh.bat를 실행하세요."
    if stage == "scanning":
        return "그래픽 경로 재검색 중 · 완료 응답을 기다립니다."
    if stage == "reloading":
        return "이미지 캐시·게임 화면 갱신 중"
    if stage == "responding":
        return "게임 갱신 결과 전달 재시도 중 · 통신 파일이 열려 있으면 닫아 주세요."
    if reason == "pack_read_in_progress":
        return "config.xml을 읽을 수 없어 잠시 기다립니다."
    if reason in ("unrecognized_or_busy_game_state", "unrecognized_game_state"):
        return "게임 대기 상태 판별 불가 · 갱신 진단을 내보내 주세요."
    if reason == "save_not_ready_or_multiple_managers":
        return "세이브를 불러온 뒤 게임 대기 상태를 확인합니다."
    if reason in ("game_busy", "game_loading_or_processing"):
        return "게임 진행·저장·경기가 끝나기를 기다립니다."
    return "게임이 안정적으로 대기하면 갱신합니다."


def failure_description(value):
    reason = str(value.get("reason", "원인 확인 필요"))
    execution = value.get("execution") or {}
    not_started = execution.get("started") is False or reason in (
        "invalid_or_expired_request", "invalid_request", "request_expired", "unsupported_game_state", "pack_not_under_registered_graphics_path") or reason.startswith("idle_wait_timeout")
    if reason == "invalid_or_expired_request":
        detail = "실행 전에 요청이 만료되거나 거부됐습니다. 플러그인 버전을 확인하세요."
    elif reason.startswith("idle_wait_timeout") or reason == "request_expired":
        detail = "갱신 가능한 게임 대기 상태를 확인하지 못해 요청이 만료됐습니다."
    elif reason == "unsupported_game_state":
        detail = "게임 상태를 판별하지 못했습니다. 갱신 진단을 내보내 주세요."
    elif reason == "pack_not_under_registered_graphics_path":
        detail = "게임이 등록한 그래픽 경로 안에서 저장 폴더를 확인하지 못했습니다."
    elif reason.startswith("scan_timeout"):
        detail = "그래픽 스캔 완료 응답이 없습니다. 갱신 진단 확인 후 게임을 다시 시작하세요."
    else:
        detail = reason
    return ("게임 갱신 실행 안 됨 · " if not_started else "게임 갱신 실패 · ") + detail + " · 파일 저장 상태와 별개입니다."


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
    if not plugin_is_current(session):
        return (directory, session), wait_description(session)
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
                evidence = value.get("execution") or {}
                if evidence.get("started") is not True or not all(type(evidence.get(key)) is int and evidence[key] >= 1
                        for key in ("rescan_attempts", "completion_callbacks", "cache_and_panel_attempts")):
                    return None, "게임 갱신 실패 · 완료 응답의 실행 기록을 확인하지 못했습니다. 갱신 진단을 내보내 주세요."
                return None, "게임 그래픽 갱신 처리 완료 · 실제 얼굴 표시를 확인하세요."
            if result == "superseded":
                return None, "더 최신 페이스팩이 있어 이전 게임 갱신 요청을 종료했습니다."
            if result == "failed":
                return None, failure_description(value)
            return pending, "게임 갱신 응답 확인 필요 · 알 수 없는 결과"
        if now - pending.get("sent_at", now) > 260:
            return None, "게임 갱신 응답 시간 초과 · 자동 재요청하지 않습니다. 갱신 진단을 확인하세요."
        return pending, "게임 그래픽 갱신 대기 · " + wait_description(session)
    if not plugin_is_current(session) or session.get("available") is not True:
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
