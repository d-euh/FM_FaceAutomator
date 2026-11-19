using FMFaceRefresh;

void Check(bool value, string message) { if (!value) throw new Exception(message); }
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
game = new FakeGame(); results.Clear();
controller = new Controller(game, () => true, (s, r) => results.Add(s));
controller.Begin(100, 1); controller.Tick(100); controller.Tick(102);
Check(game.Scans == 0 && results.Single() == "failed", "Claiming an old queued request must not extend its original expiry");
Console.WriteLine("PASS: idle gating, asynchronous completion, duplicate/late callbacks, coalescing, timeout, guards and reload failures.");

sealed class FakeGame : IGraphicsRuntime
{
    public bool Idle = true, ThrowOnReload;
    public int Scans, Reloads;
    public string BusyReason = "busy";
    public Action? Complete;
    public FrameState State() => new(Idle, Idle ? "idle" : BusyReason);
    public void Rescan(Action completed) { Scans++; Complete = completed; }
    public void ClearAndReload() { if (ThrowOnReload) throw new IOException(); Reloads++; }
}
