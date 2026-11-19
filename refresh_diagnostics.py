"""Install FM27 companions or export a combined queue/live-refresh diagnostic bundle."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

EXPECTED_BUILD = "26620374"
ROOT = Path(__file__).resolve().parent
PLUGIN_NAME = "FMFaceRefresh.Diagnostics.dll"
REPORT_PARTS = ("BepInEx", "diagnostics", "FMFaceRefresh", "refresh-diagnostic.json")
INSTALL_RECORD = ROOT / ".refresh-diagnostics.json"


def vdf_value(text, key):
    match = re.search(r'"' + re.escape(key) + r'"\s+"([^"\r\n]*)"', text, re.I)
    return match[1] if match else ""


def steam_manifest(game):
    game = Path(game).resolve()
    for manifest in sorted(game.parent.parent.glob("appmanifest_*.acf")):
        text = manifest.read_text(encoding="utf-8-sig")
        directory = vdf_value(text, "installdir")
        if directory and (manifest.parent / "common" / directory).resolve() == game:
            return {"build": vdf_value(text, "buildid"), "name": vdf_value(text, "name")}
    raise ValueError("Steam 설치 정보를 찾지 못했습니다. Steam의 ‘설치된 파일 → 찾아보기’에서 연 폴더의 fm.exe를 선택하세요.")


def validate_game(game, require_loader=True):
    game = Path(game).resolve()
    if not (game / "fm.exe").is_file() or not (game / "GameAssembly.dll").is_file():
        raise ValueError("fm.exe와 GameAssembly.dll이 있는 FM27 설치 폴더를 선택하세요.")
    manifest = steam_manifest(game)
    if manifest["name"].casefold() != "football manager 27" or manifest["build"] != EXPECTED_BUILD:
        raise ValueError(f"이 진단 설치 도구는 FM27 Steam 빌드 {EXPECTED_BUILD}용입니다. 확인된 게임: {manifest['name']} · {manifest['build']}")
    if require_loader and any(not (game / "BepInEx" / "core" / name).is_file()
                              for name in ("BepInEx.Core.dll", "BepInEx.Unity.IL2CPP.dll")):
        raise ValueError("BepInEx 6 Unity IL2CPP x64가 먼저 필요합니다. 공식 Bleeding Edge be.793 이상을 사용하세요. BepInEx 5·Mono·구형 pre.2 설치 파일은 사용하지 마세요. 기존 BepInEx를 이 도구가 교체하지는 않습니다.\n공식 다운로드: https://builds.bepinex.dev/projects/bepinex_be")
    if require_loader:
        binary = (game / "BepInEx" / "core" / "BepInEx.Core.dll").read_bytes()
        versions = re.findall(r"6\.0\.0-(be\.\d+|pre\.\d+)", binary.decode("utf-8", errors="ignore") + " " + binary.decode("utf-16le", errors="ignore"))
        if not any(value.startswith("be.") and int(value[3:]) >= 793 for value in versions):
            raise ValueError("설치된 BepInEx에서 be.793 이상을 확인하지 못했습니다. BepInEx 6 Unity IL2CPP win-x64의 정확한 버전을 확인하세요. 기존 로더는 변경하지 않았습니다.")
    return game


def find_steam_games(roots=None):
    if roots is None:
        roots = []
        if os.name == "nt":
            import winreg
            for hive, key, value in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                                     (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath")):
                try:
                    with winreg.OpenKey(hive, key) as handle:
                        roots.append(Path(winreg.QueryValueEx(handle, value)[0]))
                except OSError:
                    pass
            roots.append(Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Steam")
    libraries = {Path(root) for root in roots}
    for root in list(libraries):
        file = root / "steamapps" / "libraryfolders.vdf"
        if file.is_file():
            text = file.read_text(encoding="utf-8-sig")
            libraries.update(Path(path.replace("\\\\", "\\")) for path in re.findall(r'"path"\s+"([^"\r\n]+)"', text))
    found = set()
    for library in libraries:
        for manifest in (library / "steamapps").glob("appmanifest_*.acf"):
            text = manifest.read_text(encoding="utf-8-sig")
            if vdf_value(text, "name").casefold() == "football manager 27":
                game = manifest.parent / "common" / vdf_value(text, "installdir")
                if (game / "fm.exe").is_file():
                    found.add(game.resolve())
    return sorted(found)


def game_process_running():
    result = subprocess.run(["tasklist.exe", "/FI", "IMAGENAME eq fm.exe", "/FO", "CSV", "/NH"],
                            capture_output=True, text=True, errors="replace", timeout=20,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), shell=False)
    if result.returncode:
        raise ValueError("게임 종료 여부를 확인하지 못했습니다. Windows에서 FM27을 완전히 종료한 뒤 다시 실행하세요.")
    return any(row and row[0].casefold() == "fm.exe" for row in csv.reader(io.StringIO(result.stdout)))


def install_plugin(game, bundle=None):
    return install_component(game, bundle, PLUGIN_NAME, "FMFaceRefreshDiagnostics")


def install_component(game, bundle, filename, folder):
    game = validate_game(game)
    bundle = ROOT / "plugins" / folder if bundle is None else Path(bundle)
    source = bundle / filename
    expected = (bundle / "SHA256SUMS").read_text(encoding="ascii").split()[0]
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("진단 DLL 파일이 손상되었거나 배포 정보와 다릅니다. 저장소를 다시 업데이트하세요.")
    target = game / "BepInEx" / "plugins" / folder / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.read_bytes() != data:
        shutil.copyfile(target, target.with_suffix(".dll.previous"))
    descriptor, temporary = tempfile.mkstemp(dir=target.parent, prefix=".diagnostic-")
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(data)
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return target


def export_live_report(destination):
    from diagnostics import export_bundle
    return export_bundle(destination, root=ROOT)


def export_report(game, destination):
    source = Path(game).joinpath(*REPORT_PARTS)
    if not source.is_file():
        raise ValueError("진단 결과가 아직 없습니다. 플러그인 설치 후 FM27을 한 번 실행하고 메인 화면이 뜬 뒤 다시 눌러주세요. 계속 없으면 BepInEx/LogOutput.log를 확인하세요.")
    if source.stat().st_size > 10 * 1024 * 1024:
        raise ValueError("진단 파일의 크기가 예상 범위를 넘었습니다.")
    content = source.read_bytes()
    report = json.loads(content.decode("utf-8-sig"))
    if report.get("schema_version") != 1 or report.get("mode") != "metadata_only" or report.get("refresh_available") is not False:
        raise ValueError("이 버전의 진단 플러그인이 만든 결과가 아닙니다.")
    if report.get("detected_steam_build") != EXPECTED_BUILD:
        raise ValueError("진단한 게임 빌드가 다릅니다. Steam 업데이트 상태를 확인하세요.")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    return destination


def main():
    import argparse
    import tkinter as tk
    from tkinter import filedialog, messagebox
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    window = tk.Tk()
    window.withdraw()
    try:
        if os.name != "nt":
            raise ValueError("이 설치·내보내기 도구는 Windows용입니다.")
        if not args.export and game_process_running():
            raise ValueError("진단 플러그인 설치 전 FM27을 완전히 종료하세요. 설치 후 한 번 실행하면 진단 파일을 만듭니다.")
        if args.export:
            from diagnostics import export_bundle
            target = export_bundle(ROOT / "diagnostics" / "live-refresh-report.json", root=ROOT)
            messagebox.showinfo("문제 진단 내보내기", f"완료: {target}\n이 JSON을 대화에 첨부해 주세요. 작업 상태와 게임 갱신 기록을 함께 담았습니다.\n설정 경로가 포함되며 이미지·커스텀 지시·인증 정보는 포함하지 않습니다.")
            os.startfile(target.parent)
            return
        if INSTALL_RECORD.is_file():
            game = Path(json.loads(INSTALL_RECORD.read_text(encoding="utf-8"))["game"])
        else:
            games = find_steam_games()
            if len(games) == 1:
                game = games[0]
            else:
                executable = filedialog.askopenfilename(title="FM27 설치 폴더의 fm.exe 선택", filetypes=[("FM27", "fm.exe")])
                if not executable:
                    return
                game = Path(executable).parent
        target = install_component(game, None, "FMFaceRefresh.dll", "FMFaceRefresh") if args.live else install_plugin(game)
        INSTALL_RECORD.write_text(json.dumps({"game": str(game)}, ensure_ascii=False), encoding="utf-8")
        if args.live:
            messagebox.showinfo("게임 갱신 실험 플러그인 설치 완료", f"{target}\n\n1. FM27을 실행하고 세이브를 불러오세요.\n2. 앱의 폴더 · 연결에서 ‘생성 후 게임 그래픽 갱신’을 체크하고 저장하세요.\n3. ‘게임 갱신 테스트’를 누르고 실제 얼굴 표시를 확인하세요.\n\n실험 기능입니다. 실패하면 export_live_refresh_report.bat로 진단을 내보내 주세요.")
        else:
            messagebox.showinfo("진단 플러그인 설치 완료", f"{target}\n\n1. FM27을 실행해 메인 화면까지 기다리세요.\n2. export_refresh_diagnostics.bat를 실행하세요.\n3. 열린 폴더의 live-refresh-report.json을 대화에 첨부해 주세요.\n\n이 플러그인은 정보만 읽습니다. 아직 실시간 적용을 실행하지 않습니다.")
    except Exception as exc:
        messagebox.showerror("FM27 실시간 적용 진단", str(exc))
    finally:
        window.destroy()


if __name__ == "__main__":
    main()
