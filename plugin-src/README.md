# FM27 실시간 그래픽 갱신 사전 진단 · 0.1.0

후속 **0.2.0 실험 갱신 플러그인**과 앱 연동은 [실험 기능 안내](FMFaceRefresh/README.md)에 있습니다. 아래 내용은 원래의 읽기 전용 진단 플러그인 설명입니다.

대상은 Windows Steam **26620374 / FM27 27.1.0 계열**입니다. 이 배포물은 **진단 전용**입니다. 페이스온 실시간 적용, 게임 함수 호출, 캐시 초기화, 후킹은 구현하지 않습니다. 일반 앱의 PNG·config.xml 저장 동작은 바꾸지 않습니다.

FM26용 [FM Graphics Reload](https://github.com/dev-junos/FM-Graphics-Reload)는 `SI.Core.ResourcesSubsystem.RegisterLocalPath`, 비동기 열거 완료, `SI.Bindable.PanelManager.ReloadPanels`를 사용합니다. FM27에서 같은 이름을 찾았다는 것만으로 같은 인자·동작·완료 조건을 보장할 수 없습니다. 이 진단은 실제 사용자 설치의 생성된 interop 메타데이터를 확인하는 첫 단계입니다. 메서드 주소를 FM26에서 복사하지 않습니다.

## 사용 순서

1. FM27을 완전히 종료합니다. 앱 저장소를 업데이트합니다.
2. **BepInEx 6 Unity IL2CPP win-x64, be.793 이상**이 필요합니다. 이미 설치되어 있으면 다시 설치하지 않습니다. 없으면 [BepInEx 공식 BE 페이지](https://builds.bepinex.dev/projects/bepinex_be)에서 해당 패키지를 받고 `fm.exe` 옆에 설치합니다. BepInEx 5, Mono, 구형 6.0.0-pre.2는 사용하지 않습니다. 기존 플러그인 배포물의 별도 로더 설치 안내가 있다면 함께 확인하세요.
3. `install_refresh_diagnostics.bat`를 실행합니다. Steam 라이브러리와 FM27을 자동으로 찾으며 후보가 여러 개이거나 찾지 못하면 `fm.exe`를 선택합니다. 빌드 ID와 IL2CPP 로더를 확인한 뒤 **진단 DLL 하나만** 설치합니다. 로더·다른 플러그인·게임 파일을 교체하지 않습니다. 실행 중인 게임에는 설치하지 않습니다.
4. FM27을 실행하고 메인 화면까지 기다립니다. BepInEx가 처음 설치되었으면 interop 생성으로 첫 실행이 오래 걸릴 수 있습니다. 세이브 로드는 필요하지 않습니다.
5. `export_refresh_diagnostics.bat`를 실행합니다. `D:\FMFaceAutomator\diagnostics\refresh-diagnostic.json`을 만들고 폴더를 엽니다. 설치 경로가 다르면 해당 앱 폴더의 `diagnostics`입니다.
6. **JSON 하나만** 대화에 첨부합니다. FM 게임 DLL이나 세이브를 보낼 필요가 없습니다.

진단이 없으면 게임 설치 폴더의 `BepInEx\LogOutput.log`에서 `FM Face Refresh Diagnostics`를 확인합니다. 이 플러그인이 로드되지 않았는지, 로더 초기화가 실패했는지 구분해야 합니다. 진단 플러그인의 최초 로드에는 게임 시작이 한 번 필요합니다.

## 파일과 수집 범위

- 설치 DLL: `BepInEx\plugins\FMFaceRefreshDiagnostics\FMFaceRefresh.Diagnostics.dll`
- 원래 보고서: `BepInEx\diagnostics\FMFaceRefresh\refresh-diagnostic.json`
- 앱의 설치 경로 기록: `.refresh-diagnostics.json` (Git 제외)
- 내보낸 보고서: `diagnostics\refresh-diagnostic.json` (Git 제외)

보고서는 Steam 빌드 ID, 로더 버전, 게임 바이너리의 SHA-256, 그래픽 관련 타입·메서드·인자·필드 이름과 형식, 읽기 오류 유형을 기록합니다. **원본 게임 파일, 선수 정보, 세이브, 이미지, 전체 설치 경로는 넣지 않습니다.** 네트워크 전송은 하지 않습니다. 사용자가 직접 첨부합니다.

`mode=metadata_only`, `refresh_available=false`를 항상 기록합니다. `build_matches=true`는 빌드 ID 일치만 뜻하며 갱신 지원 판정이 아닙니다. 함수 목록과 실제 비동기 완료·캐시 반영 동작을 확인하기 전에는 자동 갱신을 활성화하지 않습니다.

메타데이터는 `PEReader`로 파일에서 직접 읽습니다. 생성된 게임 어셈블리를 `Assembly.Load`하지 않고, 타입의 정적 생성자나 게임 메서드를 실행하지 않습니다. 파일 스캔과 해시는 백그라운드에서 한 번 계산합니다. 플러그인을 제거하려면 게임 종료 후 `BepInEx\plugins\FMFaceRefreshDiagnostics` 폴더를 삭제합니다. 다른 로더·모드 폴더는 삭제하지 않습니다.

## 빌드와 검증

SDK는 개발자에게만 필요합니다. 사용자는 저장소에 포함한 DLL을 설치하면 됩니다. 로더 DLL은 이 저장소에 포함하지 않습니다.

```powershell
dotnet build plugin-src/FMFaceRefresh.Diagnostics/FMFaceRefresh.Diagnostics.csproj -c Release -p:BepInExCoreDir="C:\FM27\BepInEx\core"
dotnet run --project plugin-src/FMFaceRefresh.Diagnostics.Tests -c Release
python -m unittest discover -s tests -p test_refresh_diagnostics.py -v
```

진단 DLL은 BepInEx 6 IL2CPP의 `BasePlugin.Load`, `Log`, `Paths` API를 참조합니다. 현재 포함한 DLL은 공식 `v6.0.0-pre.2` 아카이브를 **컴파일 참조로만** 사용했습니다. 현재 공식 소스의 해당 API와 대조했으며, 그 구형 로더를 설치하거나 배포하지 않습니다. FM27에서 필요한 런타임은 be.793 이상입니다.

Linux에서 DLL 빌드와 PE 메타데이터 검사, 인자 형식 해석, 잘못된 어셈블리 처리, 빌드 판별, 비실행 검사, 경로 비공개, 설치·내보내기 검사를 완료했습니다. **실제 Windows BepInEx be.793에서의 플러그인 로드 및 FM27 26620374에서의 결과 생성은 사용자 PC 확인이 필요합니다.** 진단이 확보되어도 실제 갱신 동작 검증이 추가로 필요합니다.

다음 구현의 목표는 `PNG·XML 저장 성공 → 로컬 갱신 요청 → 게임 대기 상태 확인 → 매핑 재등록 완료 확인 → 이미지·패널 갱신 → 응답`입니다. 요청 전송만으로 게임 적용 성공을 표시하지 않고, 갱신 실패가 이미 완료된 페이스온 저장이나 AI 재합성을 유발하지 않도록 분리해야 합니다.
