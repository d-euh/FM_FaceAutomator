using System.Diagnostics;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;
using BepInEx;
using BepInEx.Unity.IL2CPP;
using HarmonyLib;
using FMFaceRefresh.Diagnostics;

namespace FMFaceRefresh;

public sealed class RefreshRequest
{
    public int protocol { get; set; }
    public string id { get; set; } = "";
    public string session { get; set; } = "";
    public string profile { get; set; } = "";
    public string pack_dir { get; set; } = "";
    public string config_sha256 { get; set; } = "";
    public double created_at { get; set; }
    public double expires_at { get; set; }
}

[BepInPlugin("io.github.d_euh.fmface.refresh", "FM Face Refresh Experimental", "0.2.1")]
public sealed class Plugin : BasePlugin
{
    public const string Profile = "fm27-steam-26620374-v1";
    private static Plugin? instance;
    private readonly string session = Guid.NewGuid().ToString("N");
    private readonly string root = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "FMFaceAutomator", "live-refresh");
    private readonly Stopwatch clock = Stopwatch.StartNew();
    private GameRuntime? runtime;
    private Controller? controller;
    private Harmony? harmony;
    private RefreshRequest? active;
    private double lastPulse = -1;
    private bool pulsing, enabled, activeStarted;
    private string problem = "initialising";
    private string SessionDir => Path.Combine(root, "sessions", Environment.ProcessId + "-" + session);
    private static double Now => DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0;

    private static string Hash(string file)
    { using var stream = File.OpenRead(file); using var sha = SHA256.Create(); return Convert.ToHexString(sha.ComputeHash(stream)).ToLowerInvariant(); }
    private static void Write(string file, object value)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(file)!);
        var temp = file + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try { File.WriteAllText(temp, JsonSerializer.Serialize(value)); File.Move(temp, file, true); }
        finally { if (File.Exists(temp)) File.Delete(temp); }
    }

    public override void Load()
    {
        instance = this;
        try
        {
            if (!OperatingSystem.IsWindows() || !Environment.Is64BitProcess || Report.SteamBuild(Paths.GameRootPath) != Report.ExpectedBuild)
                throw new InvalidOperationException("unsupported_platform_or_steam_build");
            var hashes = new Dictionary<string, string> {
                ["fm.exe"] = "a8247abcb57f409b4b45daf28234f09aca335a34e93b753004f1d438efb02349",
                ["GameAssembly.dll"] = "3f4a26c4869d6429d2e73c276adc64bdfaf6f3c86ce44fe0de93d14683a5d7e9",
                ["fm_Data/Plugins/x86_64/game_plugin.dll"] = "d12202dd01c3911d4c4e55e778f37b2251ffb10f9cf8cecc3b9ec08ece622c6b"
            };
            foreach (var pair in hashes)
                if (Hash(Path.Combine(Paths.GameRootPath, pair.Key)) != pair.Value) throw new InvalidOperationException("game_file_hash_mismatch:" + pair.Key);
            runtime = new GameRuntime();
            controller = new Controller(runtime, () => active is not null && Current(active), Reply);
            harmony = new Harmony("io.github.d_euh.fmface.refresh");
            var manager = GameRuntime.GameType("FM.UI", "FM.UI.ContinueManagerModule");
            var proceed = manager.GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance)
                .Single(m => m.Name == "ContinueGame" && m.GetParameters().Length == 1 && m.GetParameters()[0].ParameterType.IsEnum);
            harmony.Patch(proceed, prefix: new HarmonyMethod(typeof(Plugin), nameof(ContinuePrefix)));
            foreach (var argument in new[] { "FM.UI.ContinueGameEvent", "SI.Bindable.DynamicReference" })
                harmony.Patch(GameRuntime.Method(manager, "ProcessCurrentContinueFlowState", argument), prefix: new HarmonyMethod(typeof(Plugin), nameof(ContinuePrefix)));
            harmony.Patch(GameRuntime.Method(manager, "ShouldPauseCountdown"), prefix: new HarmonyMethod(typeof(Plugin), nameof(PausePrefix)));
            harmony.Patch(GameRuntime.Method(GameRuntime.GameType("SI.Core", "SI.Core.TickSubsystem"), "Update"), postfix: new HarmonyMethod(typeof(Plugin), nameof(AfterTick)));
            enabled = true; problem = "";
            Log.LogInfo("Experimental graphics refresh bridge loaded for Steam 26620374. Waiting for app opt-in and a safe game state.");
        }
        catch (Exception exception)
        {
            harmony?.UnpatchSelf();
            problem = exception.GetBaseException().Message;
            Log.LogError("Live refresh unavailable: " + problem);
        }
        Status();
    }

    private static bool ContinuePrefix() => !(instance?.enabled == true && instance.controller?.Guarded == true);
    private static bool PausePrefix(ref bool __result)
    { if (ContinuePrefix()) return true; __result = true; return false; }
    private static void AfterTick()
    { try { instance?.Pulse(); } catch { if (instance is not null) instance.enabled = false; } }

    private void Pulse()
    {
        if (pulsing || clock.Elapsed.TotalSeconds - lastPulse < 0.25) return;
        pulsing = true; lastPulse = clock.Elapsed.TotalSeconds;
        try
        {
            if (enabled && controller is { Faulted: false })
            {
                if (active is null) Accept();
                controller.Tick(clock.Elapsed.TotalSeconds);
            }
            Status();
        }
        catch (Exception exception)
        {
            enabled = false; // Always release our Continue guard, including mailbox write failures.
            problem = exception.GetBaseException().Message;
            try { if (active is not null) Reply("failed", "bridge_io_or_runtime_error:" + exception.GetType().Name); } catch { }
            Log.LogError("Live refresh stopped: " + problem);
            try { Status(); } catch { /* Never throw back into the game tick. */ }
        }
        finally { pulsing = false; }
    }

    private void Accept()
    {
        var requests = Path.Combine(root, "requests", session);
        Directory.CreateDirectory(requests);
        var state = runtime!.State();
        problem = state.Reason;
        foreach (var file in Directory.EnumerateFiles(requests, "*.json").OrderBy(f => f, StringComparer.Ordinal).Take(256))
        {
            if (new FileInfo(file).Length > 16384) continue;
            RefreshRequest? request;
            try { request = JsonSerializer.Deserialize<RefreshRequest>(File.ReadAllText(file)); }
            catch (IOException) { continue; }
            catch (JsonException) { continue; }
            if (request is null || request.session != session || !Regex.IsMatch(request.id, "^[a-f0-9]{32}$")
                || Path.GetFileName(file) != request.id + ".json") continue;
            var response = Path.Combine(SessionDir, "responses", request.id + ".json");
            if (File.Exists(response)) { File.Delete(file); continue; }
            if (request.protocol != 1 || request.profile != Profile || request.created_at > Now + 5 || request.expires_at > Now + 240)
            { active = request; Reply("failed", "invalid_request"); File.Delete(file); continue; }
            if (request.expires_at < Now)
            { active = request; Reply("failed", state.Idle ? "request_expired" : "idle_wait_timeout:" + state.Reason); File.Delete(file); continue; }
            if (!Current(request)) { active = request; Reply("superseded", "pack_changed"); File.Delete(file); continue; }
            if (state.Reason == "unrecognized_game_state")
            { active = request; Reply("failed", "unsupported_game_state"); File.Delete(file); continue; }
            if (!state.Idle) return; // Saving, processing, matches and unknown states remain queued.
            if (!runtime.ContainsRegisteredPath(request.pack_dir))
            { active = request; Reply("failed", "pack_not_under_registered_graphics_path"); File.Delete(file); continue; }
            active = request;
            File.Delete(file); // A unique request ID is never automatically replayed after claiming.
            controller!.Begin(clock.Elapsed.TotalSeconds, request.expires_at - Now);
            activeStarted = true;
            return;
        }
    }

    private static bool Current(RefreshRequest request)
    {
        if (!Path.IsPathFullyQualified(request.pack_dir) || !Regex.IsMatch(request.config_sha256, "^[a-f0-9]{64}$")) return false;
        var config = Path.Combine(request.pack_dir, "config.xml");
        return File.Exists(config) && Hash(config) == request.config_sha256;
    }

    private void Reply(string status, string reason)
    {
        if (active is null) return;
        Write(Path.Combine(SessionDir, "responses", active.id + ".json"), new {
            protocol = 1, id = active.id, session, profile = Profile, status, reason, completed_at = Now,
            visual_result_verified = false, observations = runtime?.Observations, execution = Execution()
        });
        Log.LogInfo("Graphics refresh " + active.id + ": " + status + " / " + reason);
        active = null;
        activeStarted = false;
    }

    private object Execution() => new {
        accepted = activeStarted, started = activeStarted && controller?.ScanAttempts > 0,
        rescan_attempts = activeStarted ? controller?.ScanAttempts ?? 0 : 0,
        completion_callbacks = activeStarted ? controller?.CompletionCallbacks ?? 0 : 0,
        cache_and_panel_attempts = activeStarted ? controller?.CacheAndPanelAttempts ?? 0 : 0,
        error_detail = activeStarted ? controller?.LastError : null
    };

    private void Status() => Write(Path.Combine(SessionDir, "status.json"), new {
        protocol = 1, profile = Profile, session, pid = Environment.ProcessId, heartbeat = Now,
        plugin_version = "0.2.1", experimental = true, visual_result_verified = false,
        available = enabled && controller?.Faulted == false, stage = controller?.Stage ?? "unavailable",
        request_id = active?.id, reason = controller?.Faulted == true || activeStarted ? controller?.Reason : problem,
        observations = runtime?.Observations, execution = Execution()
    });

    public override bool Unload()
    {
        if (controller?.Guarded == true) return false;
        enabled = false; problem = "unloaded"; harmony?.UnpatchSelf(); Status(); instance = null; return true;
    }
}
