# 게임 새로고침 호환 진단

게임 패치 후 Steam 빌드·게임 파일 SHA-256·새로고침 관련 메서드 서명을
읽는 개발 진단 도구입니다. 기존 정적 메타데이터 수집 코드를 재사용합니다.
게임 DLL을 로드하거나 API를 실행하지 않으며 게임·세이브·페이스팩을 수정하지 않습니다.
어떤 새 빌드도 실제 새로고침 지원 대상으로 등록하지 않습니다.

사용자 PC의 게임 파일이 있어야 호환성을 조사할 수 있습니다.

1. 업데이트된 게임을 BepInEx와 함께 한 번 실행해 `interop`가 생성되게 한 뒤 종료합니다.
2. 앱 소스 저장소를 `git pull`로 업데이트합니다.
3. 저장소의 `export_refresh_compatibility.bat`를 실행합니다.
   기존 빌드용 `.venv`가 없으면 `setup_windows.bat`를 먼저 실행합니다.
4. 게임을 자동으로 찾지 못하면 업데이트된 게임의 `fm.exe`를 선택합니다.
5. 저장소의 `diagnostics/refresh-compatibility.json`을 대화에 첨부합니다.

보고서는 24MiB 이내이며 설치 경로·선수 목록·계정 정보나 게임 바이너리 자체를
포함하지 않습니다. 손상된 어셈블리 등 읽기 오류는 `errors`에 남습니다.
게임 업데이트 중 수집하면 실패할 수 있으므로 업데이트가 끝난 뒤 실행하세요.
`build_matches: false`는 현재 실행용 DLL의 기존 지원 빌드와 다르다는 뜻이며
이 진단 자체의 실패가 아닙니다. 보고서만으로 실제 게임 동작까지 검증되지는 않습니다.

Python 없이 직접 사용할 때는 이 폴더의 EXE를 다음과 같이 실행할 수 있습니다.
별도 .NET 설치는 필요하지 않습니다. 게임 폴더 밖의 JSON 경로를 지정하세요.

```console
FMRefreshMetadata.exe "게임 설치 폴더" "보고서 저장 폴더\refresh-compatibility.json"
```

Windows용 EXE는 교차 빌드했습니다. Linux에서는 실제 메타데이터 읽기·서명 해석·
파일 해시·입력 보존·게임 코드 비실행과 실패 시 이전 보고서 보존을 검사했습니다.
실제 Windows 실행과 새 빌드의 게임 내 새로고침은 사용자 보고서를 받은 뒤 확인합니다.

개발자 빌드 및 검사:

```console
dotnet publish plugin-src/FMRefreshMetadata -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:PublishTrimmed=false -p:EnableCompressionInSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -o build/refresh-metadata
dotnet build plugin-src/FMRefreshMetadata -c Release
dotnet run --project plugin-src/FMFaceRefresh.Diagnostics.Tests -c Release
python scripts/check_refresh_metadata.py
```

수집기 소스는 `plugin-src/FMRefreshMetadata/`, 메타데이터 리더 원본은
`plugin-src/FMFaceRefresh.Diagnostics/Report.cs`입니다. 배포 EXE의 SHA-256은
`SHA256SUMS`에 있으며 .NET 런타임 고지는 동봉된 LICENSE.TXT와 THIRD-PARTY-NOTICES.TXT입니다.
