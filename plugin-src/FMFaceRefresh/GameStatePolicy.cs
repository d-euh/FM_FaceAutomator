namespace FMFaceRefresh;

/// <summary>Names confirmed by the Steam 26620374 runtime report; no guessed FM26 names.</summary>
public static class GameStatePolicy
{
    private static readonly HashSet<string> IdleFlags = new(StringComparer.Ordinal) { "None", "NeedAction", "NeedHumanManager", "Messages" };
    private static readonly HashSet<string> IdleStates = new(StringComparer.Ordinal) { "CanContinue", "NeedAction", "NeedHumanManager", "Messages" };

    public static FrameState Check(string flags, string state, IEnumerable<string> definedFlags, IEnumerable<string> definedStates)
    {
        var knownFlags = new HashSet<string>(definedFlags, StringComparer.Ordinal);
        var knownStates = new HashSet<string>(definedStates, StringComparer.Ordinal);
        var active = flags.Split(',').Select(value => value.Trim()).ToArray();
        if (!knownStates.Contains(state) || active.Any(value => !knownFlags.Contains(value)))
            return new(false, "unrecognized_game_state");
        return IdleStates.Contains(state) && active.All(IdleFlags.Contains)
            ? new(true, "idle") : new(false, "game_busy");
    }
}
