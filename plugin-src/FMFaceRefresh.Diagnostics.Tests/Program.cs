using FMFaceRefresh.Diagnostics;
using System.Text.Json;

var root = Path.Combine(Path.GetTempPath(), "fm-refresh-report-" + Guid.NewGuid().ToString("N"));
var game = Path.Combine(root, "steamapps", "common", "Football Manager 27");
var bepinex = Path.Combine(game, "BepInEx");
var interop = Path.Combine(bepinex, "interop");
var manifest = Path.Combine(root, "steamapps", "appmanifest_test.acf");
void Check(bool result, string message) { if (!result) throw new Exception(message); }
try
{
    Directory.CreateDirectory(interop);
    File.WriteAllText(manifest, "\"AppState\" { \"installdir\" \"Football Manager 27\" \"buildid\" \"26620374\" }");
    File.Copy(typeof(Report).Assembly.Location, Path.Combine(interop, "Game.Interop.dll"));
    File.WriteAllText(Path.Combine(interop, "Broken.dll"), "not an assembly");
    File.WriteAllText(Path.Combine(game, "GameAssembly.dll"), "hash fixture");
    var data = Report.Collect(game, bepinex, "6.0.0.0");
    var json = JsonSerializer.Serialize(data);
    using var document = JsonDocument.Parse(json);
    var report = document.RootElement;
    Check(report.GetProperty("build_matches").GetBoolean(), "Steam build was not detected");
    Check(!report.GetProperty("refresh_available").GetBoolean(), "Metadata discovery must not advertise refresh");
    Check(report.GetProperty("errors").GetArrayLength() == 1, "Corrupt PE must be reported without losing other data");
    var types = report.GetProperty("candidate_assemblies")[0].GetProperty("types");
    var resource = types.EnumerateArray().Single(t => t.GetProperty("name").GetString() == "SI.Core.ResourcesSubsystem");
    var register = resource.GetProperty("methods").EnumerateArray().Single(m => m.GetProperty("name").GetString() == "RegisterLocalPath");
    Check(register.GetProperty("parameters")[0].GetString() == "String", "String parameter decoding failed");
    Check(register.GetProperty("parameters")[1].GetString() == "Boolean", "Boolean parameter decoding failed");
    Check(register.GetProperty("return_type").GetString() == "Void", "Return type decoding failed");
    Check(!File.Exists(Path.Combine(root, "executed")), "Metadata scanning must never execute static constructors");
    Check(!json.Contains(root), "Report must not expose the absolute installation path");
    Check(report.GetProperty("game_file_sha256").GetProperty("GameAssembly.dll").GetString()?.Length == 64, "Missing game fingerprint");
    File.WriteAllText(manifest, "\"installdir\" \"Football Manager 27\" \"buildid\" \"11111111\"");
    Check(Report.Collect(game, bepinex)["build_matches"] is false, "A changed build must not match");
    File.Delete(manifest);
    Check(Report.SteamBuild(game) is null, "An unknown build must remain unknown");
    Directory.Delete(interop, true);
    Check(((List<string>)Report.Collect(game, bepinex)["errors"]!).Count == 1, "Missing interop must be diagnosed");
    Console.WriteLine("PASS: Steam builds, metadata signatures, corrupt/missing interop, no execution, private paths and game hashes.");
}
finally { Directory.Delete(root, true); }

namespace SI.Core
{
    public class ResourcesSubsystem
    {
        static ResourcesSubsystem()
        {
            // Would throw if the scanner loaded or initialized this game type.
            throw new InvalidOperationException("Must never run during metadata inspection");
        }
        public void RegisterLocalPath(string folder, bool clear) => throw new NotSupportedException();
        public T[] TextureCache<T>(T[] values) => values;
    }
}
