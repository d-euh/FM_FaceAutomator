"""Check the offline CLI after building it and FMFaceRefresh.Diagnostics.Tests."""
from pathlib import Path
import tempfile,subprocess,json,sys
root=Path(__file__).resolve().parents[1]
cli=root/'plugin-src/FMRefreshMetadata/bin/Release/net8.0/FMRefreshMetadata.dll'
dotnet=sys.argv[1] if len(sys.argv) > 1 else 'dotnet'
with tempfile.TemporaryDirectory(prefix='ffa-refresh-cli-') as folder:
 tmp=Path(folder);game=tmp/'steamapps/common/Football Manager 27';interop=game/'BepInEx/interop'
 interop.mkdir(parents=True)
 (tmp/'steamapps/appmanifest_test.acf').write_text('"name" "Football Manager 27" "installdir" "Football Manager 27" "buildid" "26797085"')
 fixture=root/'plugin-src/FMFaceRefresh.Diagnostics.Tests/bin/Release/net8.0/FMFaceRefresh.Diagnostics.Tests.dll'
 (interop/'Test.Interop.dll').write_bytes(fixture.read_bytes())
 (interop/'Broken.dll').write_bytes(b'not an assembly')
 for name in ['fm.exe','GameAssembly.dll','fm_Data/Plugins/x86_64/game_plugin.dll']:
  path=game/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'MZ hash fixture')
 before={str(p):p.read_bytes() for p in game.rglob('*') if p.is_file()}
 output=tmp/'report.json'
 subprocess.run([dotnet,str(cli),str(game),str(output)],check=True,capture_output=True)
 d=json.loads(output.read_text())
 assert d['detected_steam_build']=='26797085' and d['build_matches'] is False
 assert d['game_methods_invoked'] is False and d['refresh_available'] is False
 assert len(d['game_file_sha256'])==3 and len(d['errors'])==1
 types=d['candidate_assemblies'][0]['types']
 resource=next(t for t in types if t['name']=='SI.Core.ResourcesSubsystem')
 method=next(m for m in resource['methods'] if m['name']=='RegisterLocalPath')
 assert method['parameters']==['String','Boolean']
 assert str(game) not in output.read_text()
 assert before=={str(p):p.read_bytes() for p in game.rglob('*') if p.is_file()}
 inside=game/'must-not-write.json'
 assert subprocess.run([dotnet,str(cli),str(game),str(inside)],capture_output=True).returncode==1
 assert not inside.exists()
 (game/'fm.exe').unlink();old=output.read_bytes()
 assert subprocess.run([dotnet,str(cli),str(game),str(output)],capture_output=True).returncode==1
 assert output.read_bytes()==old
 print('PASS: new-build metadata/hashes, decoded signatures, corrupt assembly reporting, no game writes/execution, output boundaries and failure preservation')
