; Compile with Inno Setup 6.3+ using the definitions supplied by the builder.
[Setup]
AppId={{8AC53D3B-4059-4CBB-85C6-37492AF5B543}
AppName=FM Face Automator
AppVersion={#AppVersion}
VersionInfoVersion={#FFAVersionInfo}
DefaultDirName={code:DefaultInstallDir}
DefaultGroupName=FM Face Automator
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0
OutputDir={#FFAOutputDir}
OutputBaseFilename=FMFaceAutomator-Setup-v{#AppVersion}
SetupIconFile={#FFAIcon}
UninstallDisplayIcon={app}\FMFaceAutomator.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
CloseApplicationsFilter=*.exe,*.dll,*.pyd
RestartApplications=no
InfoBeforeFile={#FFAReadme}

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕화면 바로가기 만들기"; GroupDescription: "바로가기:"

[Files]
; This explicit list is generated from the verified release manifest.
; No config/state/facepack wildcards and no InstallDelete/UninstallDelete rules.
#include FFAFiles

[Icons]
Name: "{group}\FM Face Automator"; Filename: "{app}\FMFaceAutomator.exe"; WorkingDir: "{app}"
Name: "{group}\게임 연동 DLL 설치"; Filename: "{app}\FMFaceTools.exe"; Parameters: "--install-all"; WorkingDir: "{app}"
Name: "{group}\FM Face Automator 제거"; Filename: "{uninstallexe}"
Name: "{autodesktop}\FM Face Automator"; Filename: "{app}\FMFaceAutomator.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\FMFaceTools.exe"; Parameters: "--install-all"; Description: "게임 연동 DLL 설치 (FM27 종료·BepInEx 설치 필요)"; Flags: postinstall unchecked skipifsilent waituntilterminated
Filename: "{app}\FMFaceAutomator.exe"; Description: "FM Face Automator 실행"; Flags: postinstall nowait skipifsilent

[Code]
#include FFABackupList

function GetFileAttributesW(FileName: String): LongWord;
  external 'GetFileAttributesW@kernel32.dll stdcall';

function IsLinkedPath(Path: String): Boolean;
var
  Attr: LongWord;
  Parent: String;
begin
  Result := False;
  while Path <> '' do begin
    Attr := GetFileAttributesW(Path);
    if (Attr <> $FFFFFFFF) and ((Attr and $400) <> 0) then begin
      Result := True;
      Exit;
    end;
    Parent := ExtractFileDir(Path);
    if Parent = Path then Exit;
    Path := Parent;
  end;
end;

function CheckInstallDir(Target: String): String;
begin
  Result := '';
  if (CompareText(Target, AddBackslash(ExtractFileDrive(Target))) = 0) or
     (DirExists(AddBackslash(Target) + '_internal') and
      not FileExists(AddBackslash(Target) + 'FMFaceAutomator.exe')) then
    Result := '드라이브 루트나 다른 프로그램의 폴더가 아닌 FM Face Automator 전용 폴더를 선택하세요.';
end;

function DefaultInstallDir(Param: String): String;
begin
  if DirExists('D:\') then
    Result := 'D:\FMFaceAutomator'
  else
    Result := ExpandConstant('{localappdata}\Programs\FMFaceAutomator');
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Error: String;
begin
  Result := True;
  if CurPageID <> wpSelectDir then Exit;
  Error := CheckInstallDir(ExpandFileName(WizardDirValue));
  if Error <> '' then begin
    MsgBox(Error, mbError, MB_OK);
    Result := False;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Files: TStringList;
  Index: Integer;
  Source, Target, BackupDir: String;
begin
  Result := CheckInstallDir(ExpandFileName(ExpandConstant('{app}')));
  if Result <> '' then Exit;
  Files := TStringList.Create;
  try
    AddProgramFiles(Files);
    for Index := 0 to Files.Count - 1 do begin
      if IsLinkedPath(AddBackslash(ExpandConstant('{app}')) + Files[Index]) then begin
        Result := '설치 경로에 링크·정션이 있습니다. 일반 폴더를 선택하세요.';
        Exit;
      end;
    end;
    if IsLinkedPath(ExpandConstant('{app}\program-backups')) then begin
      Result := '프로그램 백업 경로에 링크·정션이 있습니다. 일반 폴더를 사용하세요.';
      Exit;
    end;
    if not FileExists(ExpandConstant('{app}\FMFaceAutomator.exe')) then Exit;
    BackupDir := ExpandConstant('{app}\program-backups\') + GetDateTimeString('yyyymmdd-hhnnss', #0, #0);
    while DirExists(BackupDir) do BackupDir := BackupDir + '-1';
    for Index := 0 to Files.Count - 1 do begin
      Source := AddBackslash(ExpandConstant('{app}')) + Files[Index];
      if FileExists(Source) then begin
        Target := AddBackslash(BackupDir) + Files[Index];
        if not ForceDirectories(ExtractFileDir(Target)) then begin
          Result := '프로그램 파일 백업 폴더를 만들지 못했습니다. 쓰기 권한과 여유 공간을 확인하세요.';
          Exit;
        end;
        if not FileCopy(Source, Target, False) then begin
          Result := '프로그램 파일을 백업하지 못했습니다. 앱·도구를 종료하고 쓰기 권한과 여유 공간을 확인하세요.';
          Exit;
        end;
      end;
    end;
    Log('Program file backup: ' + BackupDir);
  finally
    Files.Free;
  end;
end;
