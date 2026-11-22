using System.Text.Json;
using System.Text.RegularExpressions;

namespace FMTeamBindings;

public sealed class TeamReadRequest
{
    public int protocol { get; set; }
    public string id { get; set; } = "";
    public string session { get; set; } = "";
    public string profile { get; set; } = "";
    public string snapshot { get; set; } = "";
    public int epoch { get; set; }
    public int[] teams { get; set; } = Array.Empty<int>();
    public double created_at { get; set; }
    public double expires_at { get; set; }
}
public sealed class TeamReadService
{
    public const string Profile = "fm27-steam-26620374-teams-v1";
    private readonly string root, session = Guid.NewGuid().ToString("N");
    private readonly TeamQueryRuntime runtime;
    private readonly BindingObserver observer;
    private TeamReadRequest? active;
    private TeamProbe? controller;
    private string? activePath;
    private int activeEpoch, epoch, contextEpoch;
    private bool lastContextUnsafe;
    private bool lastIdle, faulted;
    private int? lastHuman;
    private double lastStatus;
    private object? pendingReply;
    public bool Dirty { get; set; }
    public long completed { get; private set; }
    public string reason { get; private set; } = "initialising";
    public List<object> recent { get; } = new();
    private string SessionDir => Path.Combine(root,"sessions",Environment.ProcessId + "-" + session);
    private static double Utc => DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()/1000.0;
    public TeamReadService(TeamQueryRuntime runtime, BindingObserver observer, string? root = null)
    {
        this.runtime = runtime; this.observer = observer;
        this.root = root ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"FMFaceAutomator","team-reader");
    }
    public static bool Valid(TeamReadRequest r, string session, int epoch, double now)
        => r.protocol == 1 && r.session == session && r.profile == Profile && r.epoch == epoch
            && r.id is not null && r.snapshot is not null && Regex.IsMatch(r.id,"^[a-f0-9]{32}$") && Regex.IsMatch(r.snapshot,"^[a-f0-9]{64}$")
            && r.teams is { Length: >= 1 and <= 4 } && r.teams.All(i => i >= 0) && r.teams.Distinct().Count() == r.teams.Length
            && double.IsFinite(r.created_at) && double.IsFinite(r.expires_at)
            && r.created_at <= now + 2 && now - r.created_at <= 60 && r.expires_at > now
            && r.expires_at - r.created_at is > 0 and <= 60;
    private static void Write(string file, object value)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(file)!);
        var temporary = file + ".tmp";
        try { File.WriteAllBytes(temporary,JsonSerializer.SerializeToUtf8Bytes(value)); File.Move(temporary,file,true); }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }
    public object State => new { session, epoch, context_epoch = contextEpoch, available = !faulted, reason = faulted ? "cleanup_failed_restart_required" : reason, completed, active = active?.id,
        queries_started = controller?.queries_started, recent };
    public void Tick(double elapsed, bool idle, string stateReason)
    {
        // Reusing a completed classification never authorizes native calls while busy.
        // Loading, a different manager or unknown state invalidates that evidence.
        var contextUnsafe = !idle && stateReason is not ("game_busy" or "game_processing");
        var contextChanged = lastHuman != observer.HumanTeamIndex || contextUnsafe && !lastContextUnsafe;
        if (contextChanged)
        { contextEpoch++; Dirty = true; }
        lastContextUnsafe = contextUnsafe;
        if (lastIdle && !idle || lastHuman != observer.HumanTeamIndex) { epoch++; Dirty = true; }
        lastIdle = idle; lastHuman = observer.HumanTeamIndex;
        var nextReason = !idle ? stateReason : !runtime.Ready ? "binding_owner_not_ready" : "ready";
        if (reason != nextReason) Dirty = true;
        reason = nextReason;
        if (active is not null && controller is not null)
        {
            if (activeEpoch != epoch || Utc >= active.expires_at || !File.Exists(activePath)) controller.Cancel("request_expired_cancelled_or_game_changed");
            else controller.Tick(elapsed,idle);
            if (controller.Done)
            {
                if (controller.results.Any(r => r.cleanup_error is not null)) faulted = true;
                pendingReply = new { protocol = 1, id = active.id, session, profile = Profile,
                    epoch = activeEpoch, snapshot = active.snapshot,
                    status = activeEpoch == epoch && idle && (controller.state == "complete" || controller.state == "complete_with_value_errors") ? "complete" : "unavailable",
                    results = controller.results, roots_created = runtime.temporary_roots_created,
                    roots_removed = runtime.temporary_roots_removed };
            }
            if (pendingReply is not null)
            {
                // Cleanup has already completed. Failed mailbox writes retry without
                // replaying a native query or releasing another group's handles.
                Write(Path.Combine(SessionDir,"responses",active.id + ".json"),pendingReply);
                recent.Add(new { id = active.id, epoch = activeEpoch, state = controller.state,
                    teams = active.teams, results = controller.results });
                if (recent.Count > 8) recent.RemoveAt(0);
                if (File.Exists(activePath)) File.Delete(activePath);
                completed++; Dirty = true; active = null; controller = null; pendingReply = null;
            }
        }
        if (active is null && idle && runtime.Ready && !faulted)
        {
            var requests = Path.Combine(root,"requests",session);
            Directory.CreateDirectory(requests);
            foreach (var file in Directory.EnumerateFiles(requests,"*.json").OrderBy(f => f,StringComparer.Ordinal).Take(32))
            {
                if (new FileInfo(file).Length > 16384) continue;
                TeamReadRequest? request;
                try { request = JsonSerializer.Deserialize<TeamReadRequest>(File.ReadAllText(file)); }
                catch (Exception e) when (e is IOException or JsonException) { continue; }
                if (request is null || !Valid(request,session,epoch,Utc) || Path.GetFileName(file) != request.id + ".json") continue;
                var response = Path.Combine(SessionDir,"responses",request.id + ".json");
                if (File.Exists(response)) { File.Delete(file); continue; }
                Dirty = true; active = request; activePath = file; activeEpoch = epoch;
                controller = new TeamProbe(runtime,request.teams);
                break;
            }
        }
        if (elapsed-lastStatus >= 1 || contextChanged)
        {
            Write(Path.Combine(SessionDir,"status.json"),new { protocol = 1, profile = Profile, plugin_version = "0.4.2",
                session, pid = Environment.ProcessId, epoch, context_epoch = contextEpoch, heartbeat = Utc, available = !faulted,
                idle, binding_ready = runtime.Ready, human_team_index = observer.HumanTeamIndex, reason = faulted ? "cleanup_failed_restart_required" : reason });
            lastStatus = elapsed;
        }
    }
}
