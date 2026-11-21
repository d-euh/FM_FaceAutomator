# FM Team Metadata · 0.1.0

Windows x64용 읽기 전용 메타데이터 추출기입니다. 사용자는 앱 폴더에서 `export_team_metadata.bat`를 실행합니다. 포함된 자체 런타임을 사용하므로 .NET SDK·런타임을 따로 설치하지 않습니다.

`BepInEx/interop`의 FM·SI 관리 DLL을 PE 메타데이터로 읽습니다. 게임 어셈블리를 로드하거나 생성자·메서드·속성 getter를 실행하지 않습니다. 보고서에는 형식 이름·상속 형식·속성·읽기 형태 메서드의 인자/반환 형식·숫자 enum 상수를 담습니다. 문자열 상수·메모리 주소·메서드 본문·DLL 원문·선수 정보·세이브·계정 정보는 내보내지 않습니다. 전체 설치 경로도 보고서에 넣지 않습니다.

형식 이름이 보인다는 사실만으로 해당 API의 호출 방법이나 팀 종류 판정이 검증되는 것은 아닙니다. 이 결과를 조사한 뒤 읽기 경로를 결정해야 합니다. 현재는 게임 객체를 추측해 호출하지 않습니다.

보고서에는 어셈블리당 후보 180개, 형식당 멤버 100개 제한과 원래 개수를 기록합니다. enum 숫자 값은 보존합니다. 24MiB를 초과하면 멤버 목록을 줄이고 `output_compacted=true`를 기록하며, 제한 안에 만들 수 없으면 실패합니다. 입력 DLL을 변경하지 않고 검증된 새 보고서만 이전 JSON과 교체합니다.

소스: `plugin-src/FMTeamMetadata/`. 배포 파일의 해시는 `SHA256SUMS`에 있습니다. 함께 제공한 .NET 런타임 고지는 `LICENSE.TXT`, `THIRD-PARTY-NOTICES.TXT`에 있습니다.

개발자 빌드:

```console
dotnet run --project plugin-src/FMTeamMetadata.Tests -c Release
dotnet publish plugin-src/FMTeamMetadata -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:PublishTrimmed=false -p:EnableCompressionInSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -o build/team-metadata
```

빌드한 `FMTeamMetadata.exe`를 이 폴더로 복사한 뒤 SHA256SUMS를 갱신합니다. Windows용 실행 파일은 교차 빌드했으며 실제 Windows 실행 확인은 사용자 PC에서 필요합니다. 같은 소스의 메타데이터 추출·서명 해석·enum 값·입력 보존·보고서 크기 제한은 Linux의 .NET 테스트와 CLI 실행으로 검증했습니다.
