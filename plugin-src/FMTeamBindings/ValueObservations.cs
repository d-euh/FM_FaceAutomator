using System.Text.RegularExpressions;

namespace FMTeamBindings;

// This component stores copies only. It cannot request data or change bindings.
public sealed class ValueObservations
{
    public const int Limit = 512;
    private static readonly HashSet<string> Specific = new(StringComparer.OrdinalIgnoreCase) {
        "IsFirstTeam", "IsFirstTeamAtMainClub", "TeamType", "TeamTypeStringDefault",
        "TeamTypeStringTypeOnly", "TeamTypeStringTypeOnlyAbbreviated", "Team", "Club",
        "ReservesTeam", "YouthTeam", "HighestLevelYouthTeam", "SecondHighestLevelYouthTeam",
        "YouthTeam3", "YouthTeam4", "YouthTeam5"
    };
    private static readonly HashSet<string> Contexts = new(StringComparer.OrdinalIgnoreCase) {
        "team", "club", "person", "ContextTeam", "ContextClub", "ContextPerson",
        "FirstTeam", "ReservesTeam", "YouthTeam", "YouthTeam3", "YouthTeam4", "YouthTeam5"
    };
    private readonly HashSet<string> seen = new(StringComparer.Ordinal);
    public List<ValueObservation> rows { get; } = new();
    public long dropped { get; private set; }
    public static bool Relevant(string path)
    {
        if (path.Length == 0 || path.Length > 512) return false;
        var parts = Regex.Split(path, @"[^A-Za-z0-9_]+").Where(s => s.Length > 0).ToArray();
        if (parts.Length == 0) return false;
        if (parts[0].StartsWith("FMFaceProbe", StringComparison.Ordinal)) return false;
        var name = parts[^1];
        if (Specific.Contains(name)) return true;
        return (name.Equals("Name", StringComparison.OrdinalIgnoreCase)
            || name.Equals("UniqueId", StringComparison.OrdinalIgnoreCase)
            || name.Equals("Index", StringComparison.OrdinalIgnoreCase))
            && parts.Take(parts.Length - 1).Any(Contexts.Contains);
    }
    public bool Add(string source, string path, ObservedValue value, double elapsed)
    {
        if (!Relevant(path)) return false;
        var identity = System.Text.Json.JsonSerializer.Serialize(new { path, value });
        if (!seen.Add(identity)) return false;
        if (rows.Count == Limit) { seen.Remove(identity); dropped++; return false; }
        rows.Add(new() { sequence = rows.Count + 1, elapsed_seconds = Math.Round(elapsed, 3),
            source = source, path = path, value = value });
        return true;
    }
}
public sealed class ValueObservation
{
    public int sequence { get; set; }
    public double elapsed_seconds { get; set; }
    public string source { get; set; } = "";
    public string path { get; set; } = "";
    public ObservedValue value { get; set; } = new();
}
public sealed class ObservedValue
{
    public string data_type { get; set; } = "";
    public object? scalar { get; set; }
    public bool is_null { get; set; }
    public string? numeric_kind { get; set; }
    public string? display_text { get; set; }
    public string? record_table { get; set; }
    public int? record_index { get; set; }
    public string? persistent_identity { get; set; }
    public string? error { get; set; }
}
