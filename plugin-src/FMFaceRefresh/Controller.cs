namespace FMFaceRefresh;

public interface IGraphicsRuntime
{
    FrameState State();
    void Rescan(Action completed);
    void ClearAndReload();
}

public record FrameState(bool Idle, string Reason);

/// <summary>Only called on the game tick. An asynchronous callback never touches Unity.</summary>
public sealed class Controller
{
    private readonly IGraphicsRuntime runtime;
    private readonly Func<bool> stillCurrent;
    private readonly Action<string, string> reply;
    private readonly List<Action> callbackRoots = new();
    private double deadline, stableSince = -1;
    private int completed;
    private long generation;
    private int completionCallbacks;
    public int ScanAttempts { get; private set; }
    public int CompletionCallbacks => Volatile.Read(ref completionCallbacks);
    public int CacheAndPanelAttempts { get; private set; }
    public string LastError { get; private set; } = "";
    public string Stage { get; private set; } = "idle";
    public string Reason { get; private set; } = "";
    public bool Faulted { get; private set; }
    public bool Guarded => Stage is "scanning" or "reloading";

    public Controller(IGraphicsRuntime runtime, Func<bool> stillCurrent, Action<string, string> reply)
    { this.runtime = runtime; this.stillCurrent = stillCurrent; this.reply = reply; }

    public void Begin(double now, double waitSeconds = 180)
    {
        if (Faulted || Stage != "idle") throw new InvalidOperationException("Bridge is not idle");
        Stage = "waiting"; deadline = now + Math.Clamp(waitSeconds, 0, 180); stableSince = -1; completed = 0; generation++;
        ScanAttempts = 0; completionCallbacks = 0; CacheAndPanelAttempts = 0;
        LastError = "";
    }

    public void Tick(double now)
    {
        if (Stage == "idle") return;
        try
        {
            if (now > deadline)
            {
                End("failed", Guarded ? "scan_timeout_restart_required" : "idle_wait_timeout", Guarded);
                return;
            }
            var current = stillCurrent();
            if (!current && !Guarded) { End("superseded", "pack_changed", false); return; }
            var frame = runtime.State();
            Reason = frame.Reason;
            if (Stage == "waiting")
            {
                if (!frame.Idle) { stableSince = -1; return; }
                if (stableSince < 0) stableSince = now;
                if (now - stableSince < 2) return;
                var token = generation;
                Action callback = () => {
                    if (Interlocked.Read(ref generation) == token && Interlocked.CompareExchange(ref completionCallbacks, 1, 0) == 0)
                        Volatile.Write(ref completed, 1);
                };
                callbackRoots.Add(callback); // Keep late native callbacks alive, including after failure.
                Stage = "scanning"; deadline = now + 60;
                ScanAttempts++;
                runtime.Rescan(callback);
            }
            else if (Stage == "scanning" && Volatile.Read(ref completed) != 0)
            {
                if (!current) { End("superseded", "pack_changed_after_scan", false); return; }
                if (!frame.Idle && frame.Reason == "graphics_scan_in_progress") return;
                if (!frame.Idle) { End("failed", "game_state_changed_restart_required", true); return; }
                Stage = "reloading";
                CacheAndPanelAttempts++;
                runtime.ClearAndReload();
                End("refreshed", "rescan_callback_and_panel_reload_completed", false);
            }
        }
        catch (Exception exception)
        {
            var cause = exception.GetBaseException();
            var detail = cause.GetType().Name + ": " + cause.Message;
            LastError = detail.Length > 512 ? detail[..512] : detail;
            End("failed", "runtime_error:" + cause.GetType().Name, Guarded);
        }
    }

    private void End(string result, string reason, bool fault)
    {
        Interlocked.Increment(ref generation);
        Faulted |= fault;
        Stage = "idle"; Reason = reason;
        // Bound retained callbacks; reaching this limit requires restarting rather than freeing live delegates.
        if (callbackRoots.Count >= 128) Faulted = true;
        reply(result, reason);
    }
}
