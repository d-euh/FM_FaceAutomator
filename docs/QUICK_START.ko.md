# FM Face Automator v1.0 — 설치·업데이트 안내

## 처음 설치

1. `FMFaceAutomator-v1.0-windows-x64.zip`을 내려받아 **압축을 완전히 풉니다.**
   ZIP에는 **`FMFaceAutomator-Setup-v1.0.exe`와 `README.txt`**만 들어갑니다.
   README를 읽고 Setup EXE를 실행합니다. 쓰기 가능한 전용 설치 폴더를 선택하세요.
   새 설치 기본값은 `%LOCALAPPDATA%\Programs\FMFaceAutomator`입니다.
   일반적으로 C드라이브의 사용자 AppData 아래이며 D: 등 다른 위치로 변경할 수 있습니다.
   기존 설치가 있으면 그 경로를 우선 사용하며 데이터를 자동으로 다른 드라이브로 옮기지 않습니다.
   시작 메뉴와 선택한 바탕화면 바로가기를 만들며, 설치 완료 후 앱을 실행할 수 있습니다.
2. 받는 PC에 Python, 가상환경 또는 Git은 필요하지 않습니다.
   Codex CLI와 로그인은 별도로 필요합니다. 공식 설치 안내:
   https://developers.openai.com/codex/cli/
   npm으로 설치한다면 Node.js LTS 설치 후 `npm install -g @openai/codex`를 실행합니다.
   사용 계정과 Codex 환경에서 이미지 생성 도구를 사용할 수 있어야 합니다.
3. `FMFaceAutomator.exe`를 실행하세요. 첫 실행에는 경로 검색을 마친 뒤
   **폴더 · 연결** 창이 열립니다. 세이브·기존 페이스팩·유니폼·생성 저장 위치를 확인하고
   **ChatGPT 로그인**으로 연결한 다음 **설정 저장**을 누릅니다.
   찾지 못한 경로는 **선택**으로 지정합니다. 사진·키트 자료는 배포 ZIP에 포함하지 않습니다.
4. **이적 감지 범위**를 정하고 저장한 뒤 **자동 생성 시작**을 누릅니다.
   처음 읽을 때는 기준만 기록합니다. 이후 게임의 세이브 저장에서 이동을 감지합니다.
   이적 없이 만들려면 **직접 생성**에서 선수와 유니폼 구단을 선택합니다.

## 선수단 구분·게임 새로고침 연결

- 지원 대상은 Windows x64의 **FM27 Steam 빌드 26620374**입니다.
  DLL은 기존에 검증된 `fm.exe`, `GameAssembly.dll`, `game_plugin.dll` 해시도 검사합니다.
  다른 빌드·변경된 바이너리의 지원 범위를 넓히지 않습니다.
- **BepInEx 6 Unity IL2CPP win-x64 be.793 이상**이 먼저 설치돼 있어야 합니다.
  공식 배포: https://builds.bepinex.dev/projects/bepinex_be
  BepInEx 5, Mono, 구형 pre.2는 대상이 아닙니다.
  이 앱은 기존 BepInEx를 교체하거나 다른 게임 플러그인을 삭제하지 않습니다.
- BepInEx 설치 후 게임을 한 번 실행해 초기 구성을 마치고 **FM27을 완전히 종료**합니다.
  배포 폴더의 **`install_game_plugins.bat`**를 실행하면 두 DLL을 함께 설치합니다.
  게임 위치를 못 찾으면 Steam의 **설치된 파일 → 찾아보기**에서 연 폴더의 `fm.exe`를 선택합니다.
- 개별 설치는 `install_team_bindings.bat`(팀 조회 0.4.2),
  `install_live_refresh.bat`(새로고침 0.2.3)입니다. 배포본의 배치파일은
  함께 들어 있는 `FMFaceTools.exe`를 사용하므로 Python이 필요하지 않습니다.
- 게임을 다시 실행해 앱에 연결한 세이브를 불러옵니다.
  홈의 **페이스온 새로고침**으로 실제 게임 반영을 확인합니다.
  자동 반영은 버튼 오른쪽 **생성 후 자동 새로고침**을 켜고 **설정 저장**합니다.
  선수단을 제한했을 때 구분을 확인하지 못하면 AI 호출 없이 대기·제외 처리합니다.

## 기존 설치 업데이트 — 설정·작업 기록 유지

1. 기존 앱과 도구를 종료합니다. 게임 DLL도 업데이트한다면 FM27도 종료하세요.
2. 새 ZIP을 풀고 **Setup EXE**를 실행합니다.
3. 설치 위치로 기존 `FMFaceAutomator.exe`가 있는 폴더를 선택합니다.
   기존 설치 프로그램으로 설치한 경로는 자동으로 제안하며, 이전 포터블 설치는 직접 선택합니다.
4. 설치 프로그램은 검증된 배포 목록의 프로그램 파일만 교체합니다.
   `config.json`, `state`, `workspaces`, 페이스팩, 사용자 사진·유니폼 및 관련 없는 파일은
   목록에 넣거나 덮어쓰거나 삭제하지 않습니다. 사용 중인 프로그램은 먼저 종료해야 합니다.
   기존 프로그램 파일은 설치 폴더의 `program-backups`에 백업합니다.
   백업에 실패하면 설치를 시작하지 않습니다. 정상 확인 후 불필요한 백업은 직접 정리할 수 있습니다.
5. 설치 후 앱을 실행하고 설정과 대기열이 유지됐는지 확인하세요.
   게임 DLL이 바뀐 릴리스라면 기존 설치 폴더의 DLL 설치 도구도 다시 실행합니다.

기존 앱을 `dist\FMFaceAutomator`에서 사용하고 있었다면 업데이트 대상으로 그 폴더를
선택할 수 있습니다. 새 빌드는 그 폴더를 삭제·덮어쓰지 않습니다.
원본 코드 사용자도 `setup_windows.bat` / `start_windows.bat` 실행 방식을 계속 사용할 수 있습니다.

### 포터블 묶음 및 제거

개발자가 `build_windows.bat --portable`로 만든 별도 포터블 ZIP은 폴더 전체를 풀어 실행합니다.
EXE만 따로 옮기지 마세요. 새 포터블 폴더의 `update_windows.bat`로 기존 설치를 업데이트할 수도 있습니다.
이 경우 프로그램 백업은 기존 설치 폴더 옆 `FMFaceAutomator-backup-*`에 남습니다.

Setup으로 설치한 앱은 Windows의 설치된 앱이나 시작 메뉴에서 제거합니다.
제거는 등록된 프로그램 파일·바로가기를 대상으로 하며 사용자 설정·작업 기록·페이스팩·백업과
게임 폴더에 설치한 DLL·BepInEx는 자동 삭제하지 않습니다.

## 문제 확인

- 경로가 비어 있으면 폴더 · 연결에서 직접 선택하고 저장합니다.
- Codex 실행 파일이 없거나 로그인되지 않았다면 Codex 설치와 ChatGPT 로그인을 확인합니다.
- 팀 구분 연결이 안 되면 DLL 설치, 지원 게임 빌드와 동일 세이브 로드를 확인합니다.
  임의로 1군·리저브·유소년으로 추측해 처리하지 않습니다.
- 게임 진행·저장 중에는 연동 작업이 **게임 대기** 상태로 기다릴 수 있습니다.
  안정된 뒤 재개하며, 보관된 생성 결과가 있으면 유료 합성을 다시 호출하지 않습니다.
- **폴더 · 연결 → 문제 해결 펼치기 → 문제 진단 저장** 또는
  `export_diagnostics.bat`로 JSON을 저장합니다. 경로·작업 상태가 포함되며
  사진, 공통·개별 지시, Codex 인증 정보는 포함하지 않습니다.
- 추가 조사가 필요할 때는 `export_team_bindings.bat`와 `export_team_metadata.bat`로
  기존 팀 조회 보고서·읽기 전용 메타데이터 보고서를 저장할 수 있습니다. 두 도구도 Python이 필요하지 않습니다.

## 배포 전 확인 범위

자동 테스트와 모의 파일 검증은 실제 Windows EXE 실행·실제 게임 동작 확인과 다릅니다.
배포자는 Windows x64에서 새 PC 설치, DLL 설치, 로그인, 수동 생성, 세이브 이적 감지,
게임 새로고침을 확인하고, 기존 설치 업데이트 후 설정·대기열·기존 PNG/XML 보존을 확인하세요.
빌드 성공만으로 실제 게임 검증이 완료된 것으로 안내하지 마세요.

## 개발자 빌드

Windows x64의 64비트 Python 3.12 이상에서 `setup_windows.bat`를 실행합니다.
개발자 PC에 **Inno Setup 6.3 이상**(https://jrsoftware.org/isdl.php)을 설치하고 `build_windows.bat`를 실행합니다.
컴파일러를 못 찾으면 `build_windows.bat --iscc "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"`로 지정합니다.
빌드는 매번 임시 위치에서 수행하고 두 실행 파일의 아이콘·시작과 필수 배포 파일을 검사한 뒤 설치 EXE를 만듭니다.
성공 결과는 **`dist\FMFaceAutomator-v1.0-windows-x64.zip`**이며 설치 EXE와 README.txt만 포함합니다.
`--portable` 옵션은 Inno Setup 없이 **`dist\FMFaceAutomator-Portable-v1.0-windows-x64.zip`**을 만듭니다.
기존 `dist\FMFaceAutomator`와 그 안의 사용자 데이터는 변경하지 않습니다.
새 ZIP에는 사용자 설정·작업 기록·개인 자료를 넣지 않습니다.
