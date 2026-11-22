using System.Diagnostics;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using BepInEx;
using BepInEx.Unity.IL2CPP;
using HarmonyLib;
using FMFaceRefresh.Diagnostics;

namespace FMTeamBindings;

[BepInPlugin("io.github.d_euh.fmface.teambindings", "FM Team Reader", "0.4.1")]
public sealed class Plugin : BasePlugin
{
    private static Plugin? instance;
    private Harmony? harmony, observerHarmony;
    private BindingObserver? observer;
    private TeamQueryRuntime? teamRuntime;
    private TeamReadService? teamService;
    private QueryState? queryState;
    private double lastQueryCheck, ownerDiscoveryUntil = 600;
    private string observerState = "initialising";
    private double lastSaved;
    private bool schemaSucceeded;
    private const double CaptureSeconds = 600;
    private readonly Stopwatch clock = Stopwatch.StartNew();
    private readonly List<SchemaResult> schemas = new();
    private readonly List<object> shapes = new(), errors = new();
    private Descriptors.Scan? scan;
    private int next, descriptorCalls;
    private bool busy, finished, pulsing;
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
            kind = "fm_team_bindings", schema_version = 1, tool_version = "0.4.1", state,
            mode = "runtime_team_reader_service", generated_at_utc = DateTime.UtcNow,
            detected_steam_build = Report.SteamBuild(Paths.GameRootPath),
            game_data_query_attempted = teamRuntime?.groups_created > 0,
            gameplay_state_modified = false, save_files_modified = false,
            temporary_binding_tree_modified = teamRuntime?.temporary_roots_created > 0,
            service = teamService?.State,
            probe = new { state = teamService is null ? "unavailable" : "service_ready", human_team_index = observer?.HumanTeamIndex,
                api_stage = TeamQueryRuntime.InitialisationStage, safe_game_state = queryState?.Reason,
                maximum_group_size = teamRuntime?.maximum_group_size,
                groups_created = teamRuntime?.groups_created ?? 0, groups_disposed = teamRuntime?.groups_disposed ?? 0,
                roots_created = teamRuntime?.temporary_roots_created ?? 0, roots_removed = teamRuntime?.temporary_roots_removed ?? 0 },
            schema_methods_invoked = descriptorCalls > 0, descriptor_call_attempts = descriptorCalls, schemas, types = shapes, errors,
            observations = new {
                state = observerState, capture_limit_seconds = CaptureSeconds,
                elapsed_seconds = Math.Round(clock.Elapsed.TotalSeconds, 2),
                observed_existing_ui_values_only = true, values = observer?.Values.rows,
                dropped = observer?.Values.dropped ?? 0,
                seen_events = observer?.seen_events ?? 0, inspected_events = observer?.inspected_events ?? 0,
                skipped_for_frame_budget = observer?.skipped_for_frame_budget ?? 0,
                read_errors = observer?.read_errors ?? 0, event_counts = observer?.event_counts
            },
            notice = "Schema descriptors, observed UI values and a bounded targeted team-read probe. Team queries are bounded local app requests, not slot/age/type-number guesses. Probe uses and removes a private temporary binding subtree; no existing UI values, gameplay/save files, portraits, prompts or authentication data are changed. Names/IDs may be included. Not a verified production squad filter."
        });
        if (data.Length > 8 * 1024 * 1024) throw new InvalidOperationException("report_too_large");
        var temporary = Output + ".tmp";
        File.WriteAllBytes(temporary, data); File.Move(temporary, Output, true);
        lastSaved = clock.Elapsed.TotalSeconds;
        if (observer is not null) observer.Dirty = false;
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
            InstallObserver();
            try
            {
                if (observer is null) throw new InvalidOperationException("observer_unavailable");
                queryState = new QueryState(Resolve);
                var createApi = Resolve("SI.Bindable.Bindings").GetMethods().Single(m => m.Name == "Create"
                    && m.GetParameters().Length == 2 && m.GetParameters()[1].ParameterType.FullName == "SI.Bindable.Bindings+NodeFlags");
                var spanApi = createApi.GetParameters()[0].ParameterType.GetElementType()!;
                shapes.Add(Descriptors.Shape(spanApi));
                teamRuntime = new TeamQueryRuntime(Resolve, observer);
                teamService = new TeamReadService(teamRuntime,observer);
            }
            catch (Exception e) { errors.Add(new { stage = "probe_initialise", error = e.GetBaseException().GetType().Name }); }
            Log.LogInfo("Team schema/value diagnostics enabled; bounded targeted queries wait for a safe loaded game.");
        }
        catch (Exception e)
        {
            finished = true;
            errors.Add(new { stage = "initialise", error = e.GetBaseException().GetType().Name });
            try { Save("unavailable"); } catch { }
            Log.LogError("Team schema diagnostic unavailable: " + e.GetBaseException().GetType().Name);
        }
    }
    private void InstallObserver()
    {
        try
        {
            foreach (var name in new[] { "SI.Bindable.Bindings+Key", "SI.Bindable.Bindings+SetFlags", "SI.Core.TypedValue+ITypedValuePool" })
                shapes.Add(Descriptors.Shape(Resolve(name)));
            observer = new BindingObserver(Resolve);
            observerHarmony = new Harmony("io.github.d_euh.fmface.teamvalues");
            observerHarmony.Patch(observer.Get, postfix: new HarmonyMethod(typeof(Plugin), nameof(AfterGet)));
            observerHarmony.Patch(observer.SetInternal, postfix: new HarmonyMethod(typeof(Plugin), nameof(AfterSet)));
            observerState = "capturing";
        }
        catch (Exception e)
        {
            observerHarmony?.UnpatchSelf(); observer = null; observerState = "unavailable";
            errors.Add(new { stage = "observer_initialise", error = e.GetBaseException().GetType().Name });
        }
    }
    private static void AfterGet(object __instance, object[] __args, object __result)
    { instance?.Observe(__instance, __args, __result, "get"); }
    private static void AfterSet(object __instance, object[] __args)
    { if (__args.Length >= 2) instance?.Observe(__instance, __args, __args[1], "set"); }
    private void Observe(object bindings, object[] arguments, object? value, string source)
    {
        if (observer is null || arguments.Length == 0 || value is null) return;
        try { observer.Observe(bindings, arguments[0], value, source, clock.Elapsed.TotalSeconds,
            clock.Elapsed.TotalSeconds <= CaptureSeconds, clock.Elapsed.TotalSeconds <= ownerDiscoveryUntil); }
        catch { /* Diagnostics must never affect the game's UI flow. */ }
    }
    private static void Tick()
    {
        try { instance?.Pulse(); }
        catch { /* A report I/O error must not escape into the game. */ }
    }
    private void Pulse()
    {
        if (pulsing) return;
        pulsing = true;
        try { PulseCore(); }
        finally { pulsing = false; }
    }
    private void PulseCore()
    {
        observer?.NextFrame();
        if (clock.Elapsed.TotalSeconds > CaptureSeconds && observerState == "capturing")
        { observerState = "capture_finished"; if (observer is not null) observer.Dirty = true; }
        Step();
        if (finished && teamService is not null && clock.Elapsed.TotalSeconds-lastQueryCheck >= 0.25)
        {
            lastQueryCheck = clock.Elapsed.TotalSeconds;
            var idle = queryState?.Idle() is true;
            if (!idle) ownerDiscoveryUntil = clock.Elapsed.TotalSeconds + 10;
            teamService.Tick(lastQueryCheck,idle,queryState?.Reason ?? "state_unavailable");
            if (teamService.Dirty && observer is not null) { observer.Dirty = true; teamService.Dirty = false; }
        }
        if (finished && observer is not null && clock.Elapsed.TotalSeconds - lastSaved >= 2
            && (observer.Dirty || observerState == "capturing" && clock.Elapsed.TotalSeconds - lastSaved >= 10))
            Save(schemaSucceeded ? "complete" : "complete_with_errors");
    }
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
                    schemaSucceeded = errors.Count == 0 && schemas.All(s => !s.HasErrors && s.complete);
                    Save(schemaSucceeded ? "complete" : "complete_with_errors");
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
