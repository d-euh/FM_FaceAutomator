using FMFaceRefresh;
using System.Text.Json;

void Check(bool value, string message) { if (!value) throw new Exception(message); }
using var patchApi = JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "patch-api.json")));
var patchHashes = patchApi.RootElement.GetProperty("game_file_sha256").EnumerateObject()
    .ToDictionary(p => p.Name, p => p.Value.GetString()!);
Check(GameProfiles.Resolve("26797085", file => patchHashes[file]) == "fm27-steam-26797085-v1", "New profile must match the supplied game's complete hash set");
foreach (var changed in patchHashes.Keys)
{
    try { GameProfiles.Resolve("26797085", file => file == changed ? new string('0', 64) : patchHashes[file]); throw new Exception("Changed binary accepted"); }
    catch (InvalidOperationException exception) { Check(exception.Message.StartsWith("game_file_hash_mismatch:"), "Wrong changed-hash failure"); }
}
var oldHashes = new Dictionary<string, string> {
    ["fm.exe"] = "a8247abcb57f409b4b45daf28234f09aca335a34e93b753004f1d438efb02349",
    ["GameAssembly.dll"] = "3f4a26c4869d6429d2e73c276adc64bdfaf6f3c86ce44fe0de93d14683a5d7e9",
    ["fm_Data/Plugins/x86_64/game_plugin.dll"] = "d12202dd01c3911d4c4e55e778f37b2251ffb10f9cf8cecc3b9ec08ece622c6b"
};
Check(GameProfiles.Resolve("26620374", file => oldHashes[file]) == "fm27-steam-26620374-v1", "Original profile must remain supported");
try { GameProfiles.Resolve("26797085", file => oldHashes[file]); throw new Exception("Cross-build binaries accepted"); }
catch (InvalidOperationException) { }
foreach (var unknown in new string?[] { null, "99999999" })
{
    try { GameProfiles.Resolve(unknown, _ => throw new Exception("Unknown build must not hash/read files")); throw new Exception("Unknown build accepted"); }
    catch (InvalidOperationException) { }
}
var resourceMethods = patchApi.RootElement.GetProperty("types").GetProperty("SI.Core.ResourcesSubsystem").GetProperty("methods");
Check(resourceMethods.EnumerateArray().Any(m => m.GetProperty("name").GetString() == "RescanLocalPaths"
    && m.GetProperty("return_type").GetString() == "Void" && !m.GetProperty("is_static").GetBoolean()
    && m.GetProperty("parameters").EnumerateArray().Select(p => p.GetString()).SequenceEqual(new[] { "Il2CppSystem.Action" })),
    "Patch metadata must confirm the asynchronous rescan signature, not prove runtime execution");
var chosen = @"D:\Sports Interactive\Football Manager 27\Graphics\faces\Y_new";
foreach (var root in new[] { @"d:\sports interactive\football manager 27\graphics\", "D:/Sports Interactive/Football Manager 27/Graphics",
                            "file:///D:/Sports%20Interactive/Football%20Manager%2027/Graphics/", @"\\?\D:\Sports Interactive\Football Manager 27\Graphics" })
    Check(GraphicsPaths.Contains(root, chosen), "The selected D: pack must match equivalent registered path spellings: " + root);
Check(GraphicsPaths.Contains("file://server/share/Graphics", @"\\SERVER\share\Graphics\faces"), "File URL UNC roots must match Windows UNC paths");
Check(!GraphicsPaths.Contains(@"D:\Graphics", @"D:\Graphics-old\faces"), "A sibling prefix must never count as a child");
Check(!GraphicsPaths.Contains(@"D:\Graphics", @"D:\Graphics\..\Private"), "Dot segments must not bypass directory boundaries");
Check(!GraphicsPaths.Contains("https://server/Graphics", chosen), "A remote URL must not be treated as a local root");
Check(GraphicsPaths.Canonical(@"D:\Graphics\100%20literal") == "D:/Graphics/100%20literal", "Plain filenames must not be URL decoded");
var registration = new GraphicsRegistration();
var added = new List<string>();
Check(!registration.Ensure(chosen, _ => true, added.Add) && added.Count == 0, "An existing native root must not be registered twice");
Check(registration.Ensure(chosen, _ => false, added.Add) && added.Single() == chosen, "Only the selected pack may be newly registered");
Check(!registration.Ensure(chosen.ToLowerInvariant(), _ => false, added.Add) && added.Count == 1, "Path aliases must not repeatedly add the same registration");
var failedRegistration = new GraphicsRegistration();
try { failedRegistration.Ensure(chosen, _ => false, _ => throw new IOException()); throw new Exception("Expected registration failure"); }
catch (IOException) { }
Check(failedRegistration.Ensure(chosen, _ => false, _ => { }), "Failed native registration must not be remembered as success");
using var sample = JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "game-states.json")));
var reported = sample.RootElement;
var definedFlags = reported.GetProperty("flag_values").EnumerateArray().Select(v => v.GetProperty("name").GetString()!).ToArray();
var definedStates = reported.GetProperty("state_names").EnumerateArray().Select(v => v.GetString()!).ToArray();
var observed = GameStatePolicy.Check(reported.GetProperty("observed_flags").GetString()!, reported.GetProperty("observed_state").GetString()!, definedFlags, definedStates);
Check(observed.Idle, "Regression: the user's actual None / CanContinue state must be idle");
foreach (var state in new[] { "CanContinue", "NeedAction", "NeedHumanManager", "Messages" })
    Check(GameStatePolicy.Check("NeedAction, NeedHumanManager", state, definedFlags, definedStates).Idle, "Verified user-action idle states must be accepted");
foreach (var state in definedStates.Except(new[] { "CanContinue", "NeedAction", "NeedHumanManager", "Messages" }))
    Check(!GameStatePolicy.Check("None", state, definedFlags, definedStates).Idle, "Busy state must stay blocked: " + state);
foreach (var flag in definedFlags.Except(new[] { "None", "NeedAction", "NeedHumanManager", "Messages" }))
    Check(!GameStatePolicy.Check(flag, "CanContinue", definedFlags, definedStates).Idle, "Busy flag must stay blocked: " + flag);
Check(GameStatePolicy.Check("128", "CanContinue", definedFlags, definedStates).Reason == "unrecognized_game_state", "Unknown flags must fail closed");
Check(GameStatePolicy.Check("None", "FutureUnknownState", definedFlags, definedStates).Reason == "unrecognized_game_state", "Unknown states must fail closed");
var reportedGame = new FakeGame { ReportedState = observed };
var reportedController = new Controller(reportedGame, () => true, (_, _) => { });
reportedController.Begin(0); reportedController.Tick(0); reportedController.Tick(2);
Check(reportedGame.Scans == 1 && reportedController.Guarded, "The reported real idle state must reach a scan, not expire before starting");
var inbox = GameStatePolicy.Check(reported.GetProperty("observed_inbox_flags").GetString()!, reported.GetProperty("observed_inbox_state").GetString()!, definedFlags, definedStates);
Check(inbox.Idle, "Regression: the actual Messages / Messages inbox must not expire as game_busy");
foreach (var flag in new[] { "Saving", "Processing", "Match", "Waiting" })
    Check(!GameStatePolicy.Check("Messages, " + flag, "Messages", definedFlags, definedStates).Idle, "Inbox must not bypass an active busy flag: " + flag);
var inboxGame = new FakeGame { ReportedState = inbox };
var inboxResults = new List<string>();
var inboxController = new Controller(inboxGame, () => true, (status, _) => inboxResults.Add(status));
inboxController.Begin(0); inboxController.Tick(0); inboxController.Tick(2); inboxGame.Complete!(); inboxController.Tick(3);
Check(inboxGame.Scans == 1 && inboxGame.Reloads == 1 && inboxResults.Single() == "refreshed", "Inbox refresh requires the same callback and reload evidence");
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
// A Windows sharing violation on config.xml must not lose a paid/saved result or restart a native scan.
game = new FakeGame(); results.Clear();
var locked = true;
controller = new Controller(game, () => locked ? throw new IOException("sharing violation") : true, (s, _) => results.Add(s));
controller.Begin(0); controller.Tick(0); controller.Tick(10);
Check(game.Scans == 0 && controller.Reason == "pack_read_in_progress" && !controller.Faulted, "Temporary config locks must wait");
locked = false; controller.Tick(11); controller.Tick(13);
locked = true; game.Complete!(); controller.Tick(14);
Check(game.Scans == 1 && game.Reloads == 0 && controller.Guarded, "A scan callback survives a temporary config lock");
locked = false; controller.Tick(15);
Check(game.Scans == 1 && game.Reloads == 1 && results.Single() == "refreshed", "Unlocking resumes the completed scan without another native call");

// Delivery failures retry only the immutable response, never the native operation.
var mailbox = new Mailbox();
game = new FakeGame();
var deliveryLocked = true;
var delivered = 0;
controller = new Controller(game, () => true, (s, _) => {
    Check(s == "refreshed", "Successful scan result must survive delivery errors");
    mailbox.QueueReply(() => { if (deliveryLocked) throw new UnauthorizedAccessException(); delivered++; });
});
controller.Begin(0); controller.Tick(0); controller.Tick(2); game.Complete!(); controller.Tick(3);
mailbox.FlushReply(); mailbox.FlushReply();
Check(mailbox.HasReply && mailbox.Failures == 2 && !controller.Guarded && !controller.Faulted, "A response sharing conflict must not disable graphics refresh or hold Continue");
Check(mailbox.Try("write_status", () => { }), "Unrelated successful status delivery remains usable");
deliveryLocked = false; mailbox.FlushReply(); mailbox.FlushReply();
Check(!mailbox.HasReply && delivered == 1 && game.Scans == 1 && game.Reloads == 1, "Send exactly one final response without re-running graphics work");
try { mailbox.Try("test", () => throw new InvalidOperationException()); throw new Exception("Unexpected runtime error was swallowed"); }
catch (InvalidOperationException) { }
Console.WriteLine("PASS: selected-pack registration, actual idle/inbox states, busy guards, callbacks, config locks, response delivery and execution evidence.");

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
