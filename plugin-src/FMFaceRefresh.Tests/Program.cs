using FMFaceRefresh;
using System.Text.Json;

void Check(bool value, string message) { if (!value) throw new Exception(message); }
using var sample = JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "game-states.json")));
var reported = sample.RootElement;
var definedFlags = reported.GetProperty("flag_values").EnumerateArray().Select(v => v.GetProperty("name").GetString()!).ToArray();
var definedStates = reported.GetProperty("state_names").EnumerateArray().Select(v => v.GetString()!).ToArray();
var observed = GameStatePolicy.Check(reported.GetProperty("observed_flags").GetString()!, reported.GetProperty("observed_state").GetString()!, definedFlags, definedStates);
Check(observed.Idle, "Regression: the user's actual None / CanContinue state must be idle");
foreach (var state in new[] { "CanContinue", "NeedAction", "NeedHumanManager" })
    Check(GameStatePolicy.Check("NeedAction, NeedHumanManager", state, definedFlags, definedStates).Idle, "Verified user-action idle states must be accepted");
foreach (var state in definedStates.Except(new[] { "CanContinue", "NeedAction", "NeedHumanManager" }))
    Check(!GameStatePolicy.Check("None", state, definedFlags, definedStates).Idle, "Busy state must stay blocked: " + state);
foreach (var flag in definedFlags.Except(new[] { "None", "NeedAction", "NeedHumanManager" }))
    Check(!GameStatePolicy.Check(flag, "CanContinue", definedFlags, definedStates).Idle, "Busy flag must stay blocked: " + flag);
Check(GameStatePolicy.Check("128", "CanContinue", definedFlags, definedStates).Reason == "unrecognized_game_state", "Unknown flags must fail closed");
Check(GameStatePolicy.Check("None", "FutureUnknownState", definedFlags, definedStates).Reason == "unrecognized_game_state", "Unknown states must fail closed");
var reportedGame = new FakeGame { ReportedState = observed };
var reportedController = new Controller(reportedGame, () => true, (_, _) => { });
reportedController.Begin(0); reportedController.Tick(0); reportedController.Tick(2);
Check(reportedGame.Scans == 1 && reportedController.Guarded, "The reported real idle state must reach a scan, not expire before starting");
var game = new FakeGame();
var results = new List<string>();
var current = true;
var controller = new Controller(game, () => current, (status, reason) => results.Add(status + ":" + reason));
controller.Begin(0); controller.Tick(0); controller.Tick(1);
Check(game.Scans == 0 && !controller.Guarded, "Must wait for stable idle without blocking gameplay");
controller.Tick(2);
Check(game.Scans == 1 && controller.Guarded && game.Reloads == 0 && results.Count == 0, "A request must not be reported as completed");
controller.Tick(3);
Check(game.Reloads == 0, "Must wait for the actual completion callback");
game.Complete!(); game.Complete(); game.Idle = false; game.BusyReason = "graphics_scan_in_progress";
controller.Tick(3.5);
Check(game.Reloads == 0 && controller.Guarded, "A callback must also wait for pending scan bookkeeping to finish");
game.Idle = true; controller.Tick(4); controller.Tick(5);
Check(game.Reloads == 1 && results.Single().StartsWith("refreshed:") && !controller.Guarded, "Duplicate callbacks must not reload twice");
Check(controller.ScanAttempts == 1 && controller.CompletionCallbacks == 1 && controller.CacheAndPanelAttempts == 1, "Execution evidence must distinguish a completed scan from queueing");

game.Idle = false; controller.Begin(10); controller.Tick(10); controller.Tick(20);
Check(game.Scans == 1, "Busy and unknown states must not scan");
game.Idle = true; controller.Tick(30); controller.Tick(32);
current = false; controller.Tick(33);
Check(controller.Guarded && results.Count == 1, "A newer pack must not abandon an in-flight callback");
game.Complete!(); controller.Tick(34);
Check(!controller.Faulted && !controller.Guarded && game.Reloads == 1 && results.Last().StartsWith("superseded:"), "A coalesced newer pack must not permanently disable refresh");

current = true; controller.Begin(40); controller.Tick(40); controller.Tick(42);
var lateCallback = game.Complete!;
controller.Tick(103);
Check(controller.Faulted && !controller.Guarded && results.Last().StartsWith("failed:scan_timeout"), "An uncertain scan must release our guard and stop future scans");
lateCallback(); controller.Tick(104);
Check(game.Reloads == 1, "A late callback must never apply after timeout");
try { controller.Begin(105); throw new Exception("An uncertain request was replayed"); }
catch (InvalidOperationException) { }

game = new FakeGame { ThrowOnReload = true };
results.Clear();
controller = new Controller(game, () => true, (s, r) => results.Add(s));
controller.Begin(0); controller.Tick(0); controller.Tick(2); game.Complete!(); controller.Tick(3);
Check(controller.Faulted && !controller.Guarded && results.Single() == "failed", "Panel/cache failures must never be acknowledged as refreshed");

game = new FakeGame { Idle = false }; results.Clear();
controller = new Controller(game, () => true, (s, r) => results.Add(s));
controller.Begin(0); controller.Tick(181);
Check(game.Scans == 0 && !controller.Faulted && results.Single() == "failed", "Waiting timeout must not invoke game functions");
Check(controller.ScanAttempts == 0 && controller.CompletionCallbacks == 0 && controller.CacheAndPanelAttempts == 0, "An expired idle wait must record zero game operations");
game = new FakeGame(); results.Clear();
controller = new Controller(game, () => true, (s, r) => results.Add(s));
controller.Begin(100, 1); controller.Tick(100); controller.Tick(102);
Check(game.Scans == 0 && results.Single() == "failed", "Claiming an old queued request must not extend its original expiry");
Console.WriteLine("PASS: actual FM27 None/CanContinue regression, all reported busy states/flags, execution evidence, callbacks, coalescing, timeout and guards.");

sealed class FakeGame : IGraphicsRuntime
{
    public bool Idle = true, ThrowOnReload;
    public int Scans, Reloads;
    public string BusyReason = "busy";
    public FrameState? ReportedState;
    public Action? Complete;
    public FrameState State() => ReportedState ?? new(Idle, Idle ? "idle" : BusyReason);
    public void Rescan(Action completed) { Scans++; Complete = completed; }
    public void ClearAndReload() { if (ThrowOnReload) throw new IOException(); Reloads++; }
}
