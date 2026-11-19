using BepInEx;
using BepInEx.Unity.IL2CPP;
using System.Reflection;
using System.Text.Json;

namespace FMFaceRefresh.Diagnostics;

[BepInPlugin("io.github.d_euh.fmface.refreshdiagnostics", "FM Face Refresh Diagnostics", "0.1.0")]
public sealed class Plugin : BasePlugin
{
    public override void Load()
    {
        // Read files only: no game method calls, hooks, patches or Unity API calls.
        // Interop generation has completed before IL2CPP plugins are loaded.
        var game = Paths.GameRootPath;
        var bepinex = Paths.BepInExRootPath;
        Log.LogInfo("Preparing a metadata-only report; live graphics refresh is NOT enabled.");
        _ = Task.Run(() =>
        {
            try
            {
                var output = Path.Combine(bepinex, "diagnostics", "FMFaceRefresh");
                Directory.CreateDirectory(output);
                var assembly = typeof(BasePlugin).Assembly;
                var report = Report.Collect(game, bepinex, assembly.GetName().Version?.ToString(),
                    assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion);
                var path = Path.Combine(output, "refresh-diagnostic.json");
                var temp = path + ".tmp";
                File.WriteAllText(temp, JsonSerializer.Serialize(report, new JsonSerializerOptions { WriteIndented = true }));
                File.Move(temp, path, true);
                Log.LogInfo($"Metadata report saved: {path}");
            }
            catch (Exception exception)
            {
                Log.LogError($"Metadata report failed: {exception.GetType().Name}. Live refresh remains disabled.");
            }
        });
    }
}
