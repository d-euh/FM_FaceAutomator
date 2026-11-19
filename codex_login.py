"""Delegate authentication and credential storage to the official Codex CLI."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

from discovery import find_codex


STATUS_TEXT = {
    "chatgpt": "ChatGPT 로그인됨 · 이 계정으로 합성을 요청합니다.",
    "other": "다른 인증 방식 사용 중 · ChatGPT 계정은 로그인 버튼으로 연결하세요.",
    "signed_out": "로그인되지 않음 · ChatGPT 로그인 버튼으로 계정을 연결하세요.",
    "unknown": "로그인 상태 확인 불가 · Codex 실행 파일과 설치 상태를 확인하세요.",
}


def resolve_codex(value, base):
    value = value.strip().strip('"')
    if not value or value == "codex":
        value = find_codex() or "codex"
    candidate = Path(value).expanduser()
    if not candidate.is_absolute() and ("/" in value or "\\" in value):
        candidate = Path(base) / candidate
    executable = shutil.which(str(candidate))
    if not executable:
        raise ValueError("Codex CLI를 찾지 못했습니다. Codex를 설치한 뒤 실행 파일을 선택하세요.")
    if Path(executable).suffix.lower() in (".cmd", ".bat", ".ps1") or (os.name == "nt" and Path(executable).suffix.lower() != ".exe"):
        raise ValueError("실제 codex.exe를 선택하세요. .cmd/.bat 실행 파일은 사용할 수 없습니다.")
    return str(Path(executable).resolve())


def login_status(executable, cwd):
    """Read CLI status only. Never return raw output, which can include API-key text."""
    try:
        result = subprocess.run([executable, "login", "status"], cwd=str(cwd), shell=False,
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding="utf-8", errors="replace", timeout=15,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0)
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    lines = {line.strip().casefold() for line in (result.stdout + "\n" + result.stderr).splitlines()}
    if result.returncode == 0:
        if "logged in using chatgpt" in lines:
            return "chatgpt"
        return "other"
    return "signed_out" if "not logged in" in lines else "unknown"


def browser_login(executable, cwd, cancel):
    """A visible Windows console preserves the CLI's URL fallback and error messages."""
    if cancel.is_set():
        return "cancelled"
    process = subprocess.Popen([executable, "login"], cwd=str(cwd), shell=False,
                               creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0) if os.name == "nt" else 0)
    while process.poll() is None:
        if cancel.wait(0.2):
            try:
                process.terminate()
            except OSError:
                pass  # The user may already have closed the login console.
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            return "cancelled"
    if process.returncode != 0:
        return "incomplete"
    return "complete" if login_status(executable, cwd) == "chatgpt" else "unconfirmed"
