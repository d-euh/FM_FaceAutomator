# FM Face Automator

FM27 세이브 저장 후 이적을 감지하여 Codex CLI로 페이스온 합성을 요청하는 독립형 Windows 데스크톱 프로그램의 **미리보기 버전(v0.3.1)**입니다.

- 내 구단·지정 구단·선수·나이별 생성 범위와 호출 상한
- 기존 페이스팩·2D 키트 폴더 검색, 경로 확인 및 직접 지정
- 전체 공통·선수별 추가 지시와 표시 이름 설정
- 350×350 건조형 PNG, 하단 선수 이름, 작업별 `config.xml` 자동 갱신
- 중복 이적 처리, 이전 상태의 결과 적용 방지, 백업·복구

## Windows에서 실행

1. 이 저장소를 `D:\FMFaceAutomator`에 내려받습니다.
2. Python 3.12 이상(Tk 및 Python Launcher 포함)을 준비합니다.
3. `setup_windows.bat`를 실행한 뒤 `start_windows.bat`를 실행합니다.
4. Codex CLI를 설치·로그인하고 앱에서 실제 `codex.exe`를 선택합니다.
5. 세이브와 원본 얼굴·유니폼 자료 폴더를 지정합니다.

Codex CLI 및 사용 계정에서 이미지 생성 도구를 사용할 수 있어야 합니다. 얼굴·키트 이미지는 저장소에 포함하지 않습니다.

## 검증 상태

Linux에서 자동 테스트 53개와 임시 자료를 사용한 데스크톱 흐름을 확인했습니다. **실제 FM27 세이브, Windows 10 실행·EXE 빌드, 사용자 계정의 실제 Codex 이미지 합성은 아직 검증하지 않았습니다.** 저장 전 게임 메모리 감지는 지원하지 않습니다.

상세 사용법, 지원 빌드, 파일 규칙과 남은 기능은 [한국어 설명서](README.ko.md)를 확인하세요.

```console
python -m unittest discover -s tests -v
```

비공식 팬 프로그램이며 Sports Interactive 또는 SEGA의 공식 제품이 아닙니다. 세이브 읽기에 fmsave, 이미지 후처리에 Pillow를 사용합니다.
