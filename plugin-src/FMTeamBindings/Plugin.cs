using System.Diagnostics;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using BepInEx;
using BepInEx.Unity.IL2CPP;
using HarmonyLib;
using FMFaceRefresh.Diagnostics;

namespace FMTeamBindings;

[BepInPlugin("io.github.d_euh.fmface.teambindings", "FM Team Binding Diagnostics", "0.1.1")]
public sealed class Plugin : BasePlugin
{
    private static Plugin? instance;
    private Harmony? harmony;
    private readonly Stopwatch clock = Stopwatch.StartNew();
    private readonly List<SchemaResult> schemas = new();
    private readonly List<object> shapes = new(), errors = new();
    private Descriptors.Scan? scan;
    private int next, descriptorCalls;
    private bool busy, finished;
    private Type? list;
    private string Output => Path.Combine(Paths.BepInExRootPath, "diagnostics", "FMTeamBindings", "team-bindings.json");
    private static Type Resolve(string name)
    {
        var assembly = name.StartsWith("FM.UI.", StringComparison.Ordinal) ? "FM.UI"
            : name.StartsWith("FM.GamePlugin.", StringComparison.Ordinal) ? "FM.GamePlugin"
            : name.StartsWith("SI.Bindable.Reference.Core.", StringComparison.Ordinal) ? "SI.Bindable.Reference.Core"
            : name.StartsWith("SI.Bindable.", StringComparison.Ordinal) ? "SI.Bindable"
            : name.StartsWith("SI.Core.", StringComparison.Ordinal) ? "SI.Core" : "SI.Interop";
        return Assembly.Load(assembly).GetType(name, true)!;
    }
    private void Save(string state)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(Output)!);
        var data = JsonSerializer.SerializeToUtf8Bytes(new {
            kind = "fm_team_bindings", schema_version = 1, tool_version = "0.1.1", state,
            mode = "runtime_schema_only", generated_at_utc = DateTime.UtcNow,
            detected_steam_build = Report.SteamBuild(Paths.GameRootPath),
            game_data_queried = false, game_state_modified = false,
            schema_methods_invoked = descriptorCalls > 0, descriptor_call_attempts = descriptorCalls, schemas, types = shapes, errors,
            notice = "Allowlisted static binding schema descriptors only. No player data, channels, game writes, portraits, or authentication data. Not a verified squad classification."
        });
        if (data.Length > 8 * 1024 * 1024) throw new InvalidOperationException("report_too_large");
        var temporary = Output + ".tmp";
        File.WriteAllBytes(temporary, data); File.Move(temporary, Output, true);
    }
    public override void Load()
    {
        instance = this;
        try
        {
            if (!OperatingSystem.IsWindows() || !Environment.Is64BitProcess || Report.SteamBuild(Paths.GameRootPath) != Report.ExpectedBuild)
                throw new InvalidOperationException("unsupported_platform_or_build");
            foreach (var (file, expected) in new[] {
                ("fm.exe", "a8247abcb57f409b4b45daf28234f09aca335a34e93b753004f1d438efb02349"),
                ("GameAssembly.dll", "3f4a26c4869d6429d2e73c276adc64bdfaf6f3c86ce44fe0de93d14683a5d7e9"),
                ("fm_Data/Plugins/x86_64/game_plugin.dll", "d12202dd01c3911d4c4e55e778f37b2251ffb10f9cf8cecc3b9ec08ece622c6b") })
            {
                using var stream = File.OpenRead(Path.Combine(Paths.GameRootPath, file));
                using var sha = SHA256.Create();
                if (Convert.ToHexString(sha.ComputeHash(stream)).ToLowerInvariant() != expected)
                    throw new InvalidOperationException("game_file_hash_mismatch:" + Path.GetFileName(file));
            }
            foreach (var name in Descriptors.References.Concat(Descriptors.SupportingTypes))
            {
                try { shapes.Add(Descriptors.Shape(Resolve(name))); }
                catch (Exception e) { errors.Add(new { stage = "type_shape", type = name, error = e.GetBaseException().GetType().Name }); }
            }
            // Resolve the actual closed list from the confirmed wrapper signature;
            // do not assume which interop assembly owns the generic collection.
            var listMethod = Resolve("FM.UI.TeamReference").GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static | BindingFlags.DeclaredOnly)
                .Single(m => m.Name == "GetPropertiesInternal" && m.ReturnType == typeof(void)
                    && m.GetParameters().Length == 1 && m.GetParameters()[0].ParameterType.IsGenericType
                    && m.GetParameters()[0].ParameterType.GetGenericTypeDefinition().FullName == "Il2CppSystem.Collections.Generic.List`1"
                    && m.GetParameters()[0].ParameterType.GetGenericArguments()[0].FullName == "SI.Bindable.Reference.Core.PropertyID");
            list = listMethod.GetParameters()[0].ParameterType;
            var tick = Resolve("SI.Core.TickSubsystem").GetMethod("Update", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance, null, Type.EmptyTypes, null);
            if (tick is null || tick.ReturnType != typeof(void)) throw new MissingMethodException("TickSubsystem.Update");
            Save("waiting_for_main_thread");
            harmony = new Harmony("io.github.d_euh.fmface.teambindings");
            harmony.Patch(tick, postfix: new HarmonyMethod(typeof(Plugin), nameof(Tick)));
            Log.LogInfo("Team schema report scheduled on main thread. No save/player data will be queried.");
        }
        catch (Exception e)
        {
            finished = true;
            errors.Add(new { stage = "initialise", error = e.GetBaseException().GetType().Name });
            try { Save("unavailable"); } catch { }
            Log.LogError("Team schema diagnostic unavailable: " + e.GetBaseException().GetType().Name);
        }
    }
    private static void Tick() { instance?.Step(); }
    private void Step()
    {
        if (busy || finished || clock.Elapsed.TotalSeconds < 30) return;
        busy = true;
        try
        {
            if (scan is null)
            {
                var name = Descriptors.References[next];
                scan = new Descriptors.Scan(Resolve(name), list!, () => descriptorCalls++);
                schemas.Add(scan.Result);
            }
            scan.Step(); // At most 32 properties / about 5 ms per tick, retaining partial rows.
            if (scan.Done)
            {
                scan = null; next++;
                if (next == Descriptors.References.Length)
                {
                    finished = true;
                    Save(errors.Count == 0 && schemas.All(s => !s.HasErrors && s.complete) ? "complete" : "complete_with_errors");
                    Log.LogInfo("Team schema report saved: " + Output);
                }
                else Save("reading_schema");
            }
        }
        catch (Exception e)
        {
            finished = true; errors.Add(new { stage = "tick", error = e.GetBaseException().GetType().Name });
            try { Save("unavailable"); } catch { }
            Log.LogError("Team schema diagnostic stopped without changing game data.");
        }
        finally { busy = false; }
        // The inert postfix stays installed until process exit. No refresh hooks are changed.
    }
}
