namespace FMTeamBindings;

public sealed class TeamProbeResult
{
    public int native_team_index { get; set; }
    public Dictionary<string, ObservedValue> values { get; set; } = new();
    public string? error { get; set; }
    public string? cleanup_error { get; set; }
}
public interface ITeamProbeRuntime
{
    bool Ready { get; }
    void Begin(int teamIndex);
    TeamProbeResult? Poll();
    void Close();
}
// Diagnostic IDs come from this user's controlled saves + native UI observations.
// They are NOT global squad meanings or production mappings.
public sealed class TeamProbe
{
    private readonly ITeamProbeRuntime runtime;
    private readonly Queue<int> pending = new();
    private double stableSince = -1, deadline;
    private int current;
    private readonly bool controlled;
    private readonly int expectedCount;
    public string state { get; private set; } = "waiting_for_safe_loaded_game";
    public List<TeamProbeResult> results { get; } = new();
    public int queries_started { get; private set; }
    public int groups_closed { get; private set; }
    public bool Done { get; private set; }
    public bool Dirty { get; set; }
    public TeamProbe(ITeamProbeRuntime runtime, IReadOnlyList<int>? requested = null)
    {
        this.runtime = runtime; controlled = requested is null;
        var indexes = requested ?? new[] { 540 };
        if (indexes.Count is < 1 or > 4 || indexes.Any(i => i < 0) || indexes.Distinct().Count() != indexes.Count)
            throw new ArgumentException("invalid_team_indexes");
        expectedCount = controlled ? 3 : indexes.Count;
        foreach (var index in indexes) pending.Enqueue(index);
    }
    public void Cancel(string reason)
    {
        if (Done) return;
        if (queries_started > results.Count)
        {
            var result = new TeamProbeResult { native_team_index = current, error = reason };
            try { runtime.Close(); groups_closed++; } catch (Exception e) { result.cleanup_error = e.GetBaseException().GetType().Name; }
            results.Add(result);
        }
        pending.Clear(); Done = true; Dirty = true; state = "cancelled";
    }
    public void Tick(double now, bool idle)
    {
        if (Done) return;
        if (controlled && now >= 600 && queries_started == results.Count)
        { Done = true; Dirty = true; state = "expired_without_safe_game"; return; }
        if (queries_started > results.Count)
        {
            TeamProbeResult? result = null;
            try
            {
                if (controlled && now >= 600) throw new InvalidOperationException("probe_window_expired");
                if (!idle) throw new InvalidOperationException("game_became_busy");
                if (now >= deadline) throw new InvalidOperationException("team_query_timeout");
                result = runtime.Poll();
            }
            catch (Exception e) { result = new() { error = e.GetBaseException().GetType().Name + ":" + Safe(e) }; }
            if (result is null) return;
            result.native_team_index = current;
            try { runtime.Close(); groups_closed++; }
            catch (Exception e) { result.cleanup_error = e.GetBaseException().GetType().Name; }
            results.Add(result); Dirty = true; stableSince = -1;
            if (result.error is not null || result.cleanup_error is not null) { Done = true; state = "failed"; return; }
            if (controlled && current == 540)
            {
                foreach (var pair in new[] { ("TeamContainer.HighestLevelYouthTeam", 28346), ("TeamContainer.SecondHighestLevelYouthTeam", 28347) })
                    if (result.values.TryGetValue(pair.Item1, out var value) && value.error is null
                        && value.record_table == "Team" && value.record_index == pair.Item2) pending.Enqueue(pair.Item2);
            }
            if (pending.Count == 0) { Done = true; state = results.Count != expectedCount ? "partial_team_tree" : results.Any(r => r.values.Values.Any(v => v.error is not null)) ? "complete_with_value_errors" : "complete"; }
            else state = "waiting_for_safe_loaded_game";
            return;
        }
        if (!idle || !runtime.Ready) { stableSince = -1; return; }
        if (stableSince < 0) stableSince = now;
        if (now - stableSince < 2) return;
        current = pending.Dequeue();
        queries_started++; Dirty = true; state = "querying"; deadline = now + 15;
        try { runtime.Begin(current); }
        catch (Exception e)
        {
            var result = new TeamProbeResult { native_team_index = current, error = e.GetBaseException().GetType().Name + ":" + Safe(e) };
            try { runtime.Close(); groups_closed++; }
            catch (Exception cleanup) { result.cleanup_error = cleanup.GetBaseException().GetType().Name; }
            results.Add(result); Done = true; state = "failed";
        }
    }
    private static string Safe(Exception e)
    {
        var text = e.GetBaseException().Message;
        return text.Length <= 80 && text.All(c => char.IsLetterOrDigit(c) || c == '_') ? text : "runtime_query_error";
    }
}
