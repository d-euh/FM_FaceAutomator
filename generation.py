"""Run Codex while servicing save checks and explicit cancellation."""
from __future__ import annotations

import os
import signal
import subprocess
import tempfile
import time


class GenerationCancelled(Exception):
    pass


def terminate_tree(process):
    if process.poll() is not None:
        return
    if os.name == 'nt':
        try:
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5, check=False)
        except (OSError, subprocess.TimeoutExpired):
            process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        if os.name != 'nt':
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.kill()
        process.wait(timeout=2)


def run_codex(command, *, input, stdout, stderr, timeout, text=True, encoding='utf-8',
              shell=False, cancel_event=None, heartbeat=None, heartbeat_interval=2):
    if shell:
        raise ValueError('Codex must run without a shell')
    if cancel_event is not None and cancel_event.is_set():
        raise GenerationCancelled()
    # A file avoids blocking on a full stdin pipe for long custom instructions.
    with tempfile.TemporaryFile() as source:
        source.write(input.encode(encoding))
        source.seek(0)
        flags = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session': True}
        process = subprocess.Popen(command, stdin=source, stdout=stdout, stderr=stderr, shell=False, **flags)
        started, checked = time.monotonic(), time.monotonic()
        try:
            while process.poll() is None:
                if cancel_event is not None and cancel_event.is_set():
                    raise GenerationCancelled()
                now = time.monotonic()
                if now - started >= timeout:
                    raise subprocess.TimeoutExpired(command, timeout)
                if heartbeat and now - checked >= heartbeat_interval:
                    heartbeat()
                    checked = time.monotonic()
                if cancel_event is not None:
                    cancel_event.wait(.1)
                else:
                    time.sleep(.1)
            if cancel_event is not None and cancel_event.is_set():
                raise GenerationCancelled()
            return subprocess.CompletedProcess(command, process.returncode)
        finally:
            terminate_tree(process)
