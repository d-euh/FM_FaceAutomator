using System.Text.Json;
using FMTeamBindings;
using FM.UI;
using SI.Bindable.Reference.Core;

void Check(bool condition, string reason) { if (!condition) throw new Exception(reason); }
var type = typeof(TeamReference);
var list = typeof(List<PropertyID>);
TeamReference.Reset();
var calls = 0;
var result = Descriptors.Read(type, list, () => calls++);
Check(result.complete && !result.HasErrors, "Realistic BindingKind wrapper must be readable");
Check(!typeof(BindingKind).IsEnum && typeof(BindingKind).BaseType?.FullName == "Il2CppSystem.ValueType", "Regression fixture must mirror actual game wrapper");
var property = result.properties[0];
Check(property.id == 0xf0102030u && property.description == "registered_team_kind" && property.name == "registered_team", "Read nonsequential IDs and description");
Check(property.kind_value == 2 && property.kind == "Reference" && property.is_list == true, "Read Kind and IsList members of wrapper");
Check(property.reference_id == 0xbeef0010 && property.reference_name == "team", "Read reference schema target, never actual player data");
Check(calls > 4 && !TeamReference.SetterCalled, "Track attempts without writing state");

TeamReference.Reset(); TeamReference.AsValue = true;
result = Descriptors.Read(type, list);
Check(!result.HasErrors && result.properties[0].value_type == "System.Int32", "Preserve scalar schema type");
Check(result.properties[0].reference_id is null, "Do not read unused reference target");

TeamReference.Reset(); TeamReference.ThrowKindFor = 0;
result = Descriptors.Read(type, list);
Check(result.complete && result.HasErrors && result.properties[0].description == "registered_team_kind", "Kind errors must not discard description/row");
Check(result.properties[0].errors.Single().stage == "binding_kind", "Need per-property error");

TeamReference.Reset(); TeamReference.FillCount = TeamReference.Count = 1500;
var scan = new Descriptors.Scan(type, list);
scan.Step(1);
Check(!scan.Done && scan.Result.scanned_count == 1, "Bound work per tick");
while (!scan.Done) scan.Step();
Check(scan.Result.complete && !scan.Result.HasErrors && scan.Result.properties.Count == 1500, "Do not reject legitimate >1024 property schemas");

foreach (var count in new[] { -1, Descriptors.Limit + 1 }) {
    TeamReference.Reset(); TeamReference.Count = count;
    result = Descriptors.Read(type, list);
    Check(!result.complete && result.declared_count == count && result.errors.Single().code == "property_count_out_of_bounds",
        "Preserve actual count even if bounds stop collection");
    Check(TeamReference.FillCalls == 0, "Do not allocate/fill on invalid count");
}
TeamReference.Reset(); TeamReference.Count = 2;
result = Descriptors.Read(type, list);
Check(!result.complete && result.count == 1 && result.declared_count == 2 && result.errors.Single().code == "property_count_mismatch", "Record both counts");
TeamReference.Reset(); TeamReference.FillCount = TeamReference.Count = 2; TeamReference.Duplicate = true;
result = Descriptors.Read(type, list);
Check(result.complete && result.properties.Count == 2 && result.properties[1].errors.Single().code == "duplicate_property_id", "Retain earlier rows on duplicate");
TeamReference.Reset(); TeamReference.Label = new string('x', 2049);
result = Descriptors.Read(type, list);
Check(result.complete && result.properties[0].errors.Single().code == "descriptor_text_too_long" && result.properties[0].reference_name == "team", "Bound descriptions independently of kind metadata");
result = Descriptors.Read(typeof(EvilReference), list);
Check(result.errors.Single().code == "reference_not_allowlisted", "Do not invoke unknown types");
result = Descriptors.Read(typeof(PersonReference), list);
Check(!result.complete && result.errors.Single().error == "MissingMethodException" && !PersonReference.Called, "Check exact signatures before invoking any native method");
Check(!Descriptors.References.Contains("FM.UI.DatabaseRecordReference"), "Record base class has no schema descriptors");
TeamReference.Reset();
var shape = JsonSerializer.SerializeToElement(Descriptors.Shape(typeof(BindingKind)));
Check(!shape.GetProperty("is_enum").GetBoolean() && shape.GetProperty("methods").EnumerateArray().Any(m => m.GetProperty("name").GetString() == "get_Kind"), "Need actual wrapper shape");
Check(!TeamReference.SetterCalled, "Shape collection cannot invoke getters/setters");
Console.WriteLine("PASS: actual BindingKind structure, reference/scalar schemas, chunked 1500 rows, preserved partial data/counts, bounds, duplicates, exact signatures, no player data/state writes.");

// Observation policy tests do not call the game or read unrelated UI values.
Check(!ValueObservations.Relevant("FMFaceProbe123.IsFirstTeam"), "Keep targeted probe separate from existing UI observations");
Check(ValueObservations.Relevant("context.person.Team.TeamType"), "Watch exact team-kind property");
Check(ValueObservations.Relevant("context.club.YouthTeam.Name"), "Watch team names in a football context");
Check(!ValueObservations.Relevant("Steam.Login.Name") && !ValueObservations.Relevant("account.Name")
    && !ValueObservations.Relevant("context.person.Password") && !ValueObservations.Relevant("ui.Name"), "Never capture unrelated UI/account fields");
var observed = new ValueObservations();
Check(observed.Add("get", "context.team.IsFirstTeam", new() { data_type = "System.Boolean", scalar = true }, 1), "Keep observed scalar");
Check(!observed.Add("set", "context.team.IsFirstTeam", new() { data_type = "System.Boolean", scalar = true }, 2), "Deduplicate same path/value across sources");
Check(observed.Add("set", "context.team.IsFirstTeam", new() { data_type = "System.Boolean", scalar = false }, 3), "Preserve value transition");
Check(!observed.Add("get", "Steam.Login.Name", new() { scalar = "secret" }, 3), "Reject unrelated path before storage");
for (int i = 2; i < ValueObservations.Limit; i++) observed.Add("get", "context.team.TeamType", new() { scalar = i }, i);
Check(!observed.Add("get", "context.team.TeamType", new() { scalar = 9999 }, 9999) && observed.rows.Count == ValueObservations.Limit && observed.dropped == 1, "Bound report storage");
Check(observed.rows[0].sequence == 1 && observed.rows[1].value.scalar is false, "Keep order and raw booleans without guessed classification");
Console.WriteLine("PASS: passive observation path allowlist, value changes, cross-source deduplication, unrelated UI exclusion and capacity bounds.");

// Use signature-compatible fake Bindings/TypedValue to verify no active reads/writes.
var observer = new BindingObserver(name => typeof(SI.Core.TypedValue).Assembly.GetType(name, true)!);
var bindings = new SI.Bindable.Bindings();
var key = new SI.Bindable.Bindings.Key { Path = "context.team.IsFirstTeam" };
observer.Observe(bindings, key, new SI.Core.TypedValue(true, "System.Boolean"), "set", 4);
Check(observer.Values.rows.Single().value.scalar is true, "Decode only already supplied values");
observer.Observe(bindings, new SI.Bindable.Bindings.Key { Path = "context.club.YouthTeam.Name" }, new SI.Core.TypedValue("Manchester U18", "System.String"), "set", 5);
Check((string?)observer.Values.rows[1].value.scalar == "Manchester U18", "Decode supplied string with AsString");
var opaque = new SI.Core.TypedValue(new object(), "Unverified.NativeValue");
observer.Observe(bindings, new SI.Bindable.Bindings.Key { Path = "context.team.TeamType" }, opaque, "set", 6);
Check(opaque.GetCalls == 0 && observer.Values.rows[2].value.error == "unsupported_data_type", "Do not reinterpret unknown native layouts");
var ignored = new SI.Core.TypedValue("secret", "System.String");
observer.Observe(bindings, new SI.Bindable.Bindings.Key { Path = "account.Name" }, ignored, "set", 7);
Check(ignored.GetCalls == 0 && observer.Values.rows.Count == 3, "Filter unrelated paths before inspecting value");
for (int i = 0; i < 150; i++) observer.Observe(bindings, key, new SI.Core.TypedValue(true, "System.Boolean"), "set", 8);
Check(observer.skipped_for_frame_budget > 0 && observer.inspected_events <= 128, "Bound native path reads per frame");
observer.NextFrame();
var broken = new SI.Core.TypedValue(3, "System.Int32") { ThrowGet = true };
observer.Observe(bindings, new SI.Bindable.Bindings.Key { Path = "context.team.TeamType" }, broken, "set", 9);
Check(observer.Values.rows[^1].value.data_type == "System.Int32" && observer.Values.rows[^1].value.error == "InvalidOperationException", "Preserve reported type when value conversion fails");
Check(bindings.ActiveCalls == 0, "Never invoke Bindings.Get/SetInternal to request or mutate game data");
var busyObserver = new BindingObserver(name => typeof(SI.Core.TypedValue).Assembly.GetType(name, true)!);
for (int pass = 0; pass < 2; pass++) {
    if (pass == 1) busyObserver.NextFrame();
    for (int i = 0; i < 1000; i++) busyObserver.Observe(bindings,
        new SI.Bindable.Bindings.Key { Path = i == 900 ? "context.team.TeamType" : "ui.Name" },
        new SI.Core.TypedValue(7, "System.Int32"), "get", 10 + pass);
}
Check(busyObserver.Values.rows.Count == 1 && busyObserver.Values.rows[0].value.scalar is 7,
    "Adaptive sampling must reach later UI events after a busy frame");
Console.WriteLine("PASS: signature-compatible passive hooks, primitive decoding, opaque-type refusal, path filtering and frame bounds; no active data requests.");

// Actual numeric wrapper conversions: retain precision and never truncate floats into IDs.
var numberObserver = new BindingObserver(name => typeof(SI.Core.TypedValue).Assembly.GetType(name, true)!);
foreach (var pair in new (SI.Core.DynamicNumber Input, object Expected)[] {
    (new SI.Core.DynamicNumber(-123L), -123L), (new SI.Core.DynamicNumber(ulong.MaxValue), ulong.MaxValue),
    (new SI.Core.DynamicNumber(2.75), 2.75) }) {
    var decoded = numberObserver.DecodeSupplied(new SI.Core.TypedValue(pair.Input, "SI.Core.DynamicNumber"));
    Check(decoded.error is null && Equals(decoded.scalar, pair.Expected), "Use explicit tagged conversion without precision loss");
}
var invalidNumber = numberObserver.DecodeSupplied(new SI.Core.TypedValue(new SI.Core.DynamicNumber(), "SI.Core.DynamicNumber"));
Check(invalidNumber.scalar is null && invalidNumber.error == "invalid_dynamic_number", "Invalid numbers cannot become player ID zero");
Check(BindingObserver.DisplayText("\u0001" + new string('x', 400) + "\u0002Manchester U18\u0001") == "Manchester U18", "Read rendered label without decoding embedded payload");

var fake = new FakeProbeRuntime();
var probe = new TeamProbe(fake);
probe.Tick(0, true); probe.Tick(2.1, true); probe.Tick(2.2, true);
probe.Tick(3, true); probe.Tick(5.1, true); probe.Tick(5.2, true);
probe.Tick(6, true); probe.Tick(8.1, true); probe.Tick(8.2, true);
Check(probe.state == "complete" && fake.Started.SequenceEqual(new[] { 540, 28346, 28347 }) && fake.Closed == 3, "Three bounded queries and cleanup");
var paused = new FakeProbeRuntime(); var pausedProbe = new TeamProbe(paused);
pausedProbe.Tick(0, false); pausedProbe.Tick(10, true); pausedProbe.Tick(11, true);
Check(paused.Started.Count == 0, "Wait for two stable idle seconds");
pausedProbe.Tick(12.1, true); pausedProbe.Tick(12.2, false);
Check(pausedProbe.state == "failed" && paused.Closed == 1, "Abort and close when game starts processing");
var stalled = new FakeProbeRuntime { Stall = true }; var stalledProbe = new TeamProbe(stalled);
stalledProbe.Tick(0, true); stalledProbe.Tick(2.1, true); stalledProbe.Tick(18, true);
Check(stalledProbe.Done && stalled.Closed == 1 && stalled.Started.Count == 1, "Timeout cannot retry or leak a read group");
var wrong = new FakeProbeRuntime { WrongChildren = true }; var wrongProbe = new TeamProbe(wrong);
wrongProbe.Tick(0, true); wrongProbe.Tick(2.1, true); wrongProbe.Tick(2.2, true);
Check(wrongProbe.state == "partial_team_tree" && wrong.Started.Count == 1, "Never query assumed indexes not returned by the main-team query");

var ownerObserver = new BindingObserver(name => typeof(SI.Core.TypedValue).Assembly.GetType(name, true)!);
var ownerBindings = new SI.Bindable.Bindings();
ownerObserver.Observe(ownerBindings, new SI.Bindable.Bindings.Key { Path = "Human.Team" }, new SI.Core.TypedValue(new FM.UI.TeamReference(540), "FM.UI.TeamReference"), "set", 20);
Check(ownerObserver.HumanTeamIndex == 540, "Bind only to an observed current team");
var query = new TeamQueryRuntime(name => typeof(SI.Core.TypedValue).Assembly.GetType(name, true)!, ownerObserver);
SI.Bindable.Bindings.MaxGroupSize = 1;
try { query.Begin(540); throw new Exception("Group limit must reject before allocation"); } catch (InvalidOperationException) { }
Check(ownerBindings.Roots == 0, "Never exceed native group limit");
SI.Bindable.Bindings.MaxGroupSize = 64;
query.Begin(540); var queryValues = query.Poll(); query.Close();
Check(queryValues?.values.Count == TeamQueryRuntime.Properties.Length && query.groups_disposed == 1
    && query.temporary_roots_created == query.temporary_roots_removed && ownerBindings.Roots == 0, "Owned temporary tree and group are removed");
ownerBindings.ThrowDispose = true;
query.Begin(540);
try { query.Close(); throw new Exception("Expected Dispose error"); } catch (InvalidOperationException) { }
Check(ownerBindings.Roots == 0, "Private root removal must still run when group Dispose throws");
ownerBindings.ThrowDispose = false;
ownerBindings.ThrowBuild = true;
try { query.Begin(540); throw new Exception("Expected Build failure"); } catch (System.Reflection.TargetInvocationException) { }
try { query.Close(); throw new Exception("Expected uncertain group cleanup report"); } catch (InvalidOperationException) { }
Check(ownerBindings.Roots == 0, "Always try to remove private root when group Build fails");
Console.WriteLine("PASS: tagged numeric conversion, stable-idle probe scheduling, bounded returned targets, timeout/busy cleanup, private binding ownership and partial-build cleanup reporting.");

// General app-driven batches do not contain the old controlled team-index rule.
var general = new FakeProbeRuntime(); var generalProbe = new TeamProbe(general,new[] { 123,456 });
generalProbe.Tick(0,true); generalProbe.Tick(2.1,true); generalProbe.Tick(2.2,true);
generalProbe.Tick(3,true); generalProbe.Tick(5.1,true); generalProbe.Tick(5.2,true);
Check(generalProbe.state == "complete" && general.Started.SequenceEqual(new[] { 123,456 }), "General batches must not query hardcoded Manchester United indexes");
var cancelRuntime = new FakeProbeRuntime { Stall = true }; var cancelled = new TeamProbe(cancelRuntime,new[] { 123 });
cancelled.Tick(0,true); cancelled.Tick(2.1,true); cancelled.Cancel("test_cancel");
Check(cancelled.Done && cancelRuntime.Closed == 1, "Cancellation cleans the active general batch");
var validRequest = new TeamReadRequest { protocol=1, profile=TeamReadService.Profile,session=new string('a',32),id=new string('b',32),
    snapshot=new string('c',64),epoch=2,teams=new[] { 123,456 },created_at=1000,expires_at=1040 };
Check(TeamReadService.Valid(validRequest,new string('a',32),2,1001), "Accept exact bounded app request");
Check(!TeamReadService.Valid(validRequest,new string('a',32),3,1001), "Reject another game epoch");
validRequest.teams=new[] { 123,123 };
Check(!TeamReadService.Valid(validRequest,new string('a',32),2,1001), "Reject duplicate targets");
validRequest.id=null!;
Check(!TeamReadService.Valid(validRequest,new string('a',32),2,1001), "Malformed request cannot crash the mailbox");
Console.WriteLine("PASS: arbitrary bounded team batches, cancellation cleanup and local request/session/epoch validation.");

var serviceFolder = Path.Combine(Path.GetTempPath(),"fm-team-service-"+Guid.NewGuid().ToString("N"));
try {
    ownerBindings.ThrowBuild = false; ownerBindings.ThrowDispose = false;
    var serviceRuntime = new TeamQueryRuntime(name => typeof(SI.Core.TypedValue).Assembly.GetType(name,true)!,ownerObserver);
    var service = new TeamReadService(serviceRuntime,ownerObserver,serviceFolder);
    service.Tick(1,true,"idle");
    var statusFile = Directory.GetFiles(Path.Combine(serviceFolder,"sessions"),"status.json",SearchOption.AllDirectories).Single();
    using var currentStatus = JsonDocument.Parse(File.ReadAllText(statusFile));
    var sid = currentStatus.RootElement.GetProperty("session").GetString()!;
    var req = new TeamReadRequest { protocol=1,id=new string('d',32),session=sid,profile=TeamReadService.Profile,
        epoch=currentStatus.RootElement.GetProperty("epoch").GetInt32(),snapshot=new string('e',64),teams=new[] { 123 },
        created_at=DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()/1000.0,expires_at=DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()/1000.0+40 };
    var inbox=Path.Combine(serviceFolder,"requests",sid); Directory.CreateDirectory(inbox);
    File.WriteAllText(Path.Combine(inbox,req.id+".json"),JsonSerializer.Serialize(req));
    service.Tick(2,true,"idle");service.Tick(2.5,true,"idle");service.Tick(4.6,true,"idle");service.Tick(4.85,true,"idle");
    var responseFile=Path.Combine(Path.GetDirectoryName(statusFile)!,"responses",req.id+".json");
    using var response=JsonDocument.Parse(File.ReadAllText(responseFile));
    Check(response.RootElement.GetProperty("status").GetString()=="complete"
        && response.RootElement.GetProperty("results")[0].GetProperty("native_team_index").GetInt32()==123,
        "File IPC drives one bounded group and returns correct correlation/target");
    Check(service.completed==1 && ownerBindings.Roots==0 && !File.Exists(Path.Combine(inbox,req.id+".json")), "IPC completion cleans request and private root");
} finally { if(Directory.Exists(serviceFolder)) Directory.Delete(serviceFolder,true); }
Console.WriteLine("PASS: local file IPC request, typed native-group adapter, response correlation and cleanup end to end with fake game API.");

namespace Il2CppSystem {
    public class ValueType { }
    public class Type { private readonly string name; public Type(string name = "System.Int32") { this.name = name; } public string FullName => name; }
    public class Object : Il2CppInterop.Runtime.InteropTypes.Il2CppObjectBase { public object? Item; }
    public class ReadOnlySpan<T> {
        public readonly string Text;
        public ReadOnlySpan(Il2CppInterop.Runtime.InteropTypes.Arrays.Il2CppStructArray<T> array) { Text = new string(array.Values.Cast<char>().ToArray()); }
    }
}
namespace SI.Bindable.Reference.Core {
    public struct PropertyID { public uint id; public uint ID => id; }
    public struct ReferenceID {
        public uint id;
        public uint ID => id;
        public ReferenceIDInfo GetInfo() => new();
    }
    public static class IdentifierUtils {
        public static string GetName<TIdentifier>(TIdentifier id) => "registered_team";
    }
    public class IdentifierInfo { public string Name => "team"; }
    public class ReferenceIDInfo : IdentifierInfo { }
    public enum Kind { Invalid = 0, Value = 1, Reference = 2 }
    public class BindingKind : Il2CppSystem.ValueType {
        public Kind Kind => FM.UI.TeamReference.AsValue ? Kind.Value : Kind.Reference;
        public ReferenceID Reference => FM.UI.TeamReference.AsValue
            ? throw new Exception("Value schemas must not read Reference") : new() { id = 0xbeef0010 };
        public Il2CppSystem.Type Type => !FM.UI.TeamReference.AsValue
            ? throw new Exception("Reference schemas must not read Type") : new();
        public bool IsList => !FM.UI.TeamReference.AsValue;
    }
}
namespace FM.UI {
    public enum DatabaseTableType { Team = 24, Club = 3 }
    public class TeamReference {
        public TeamReference() { }
        public TeamReference(int index) { Index = index; }
        public TeamReference(IntPtr pointer) { Index = 540; }
        public int Index { get; }
        public DatabaseTableType Type => DatabaseTableType.Team;
        public static int Count, FillCount, FillCalls, ThrowKindFor;
        public static bool SetterCalled, AsValue, Duplicate;
        public static string Label = "";
        public static void Reset() {
            FillCount = Count = 1; FillCalls = 0; ThrowKindFor = -1;
            SetterCalled = AsValue = Duplicate = false; Label = "registered_team_kind";
        }
        public static int GetPropertyCountInternal() => Count;
        public static void GetPropertiesInternal(List<PropertyID> target) {
            FillCalls++;
            for (int i = 0; i < FillCount; i++) target.Add(new() { id = 0xf0102030u + (Duplicate ? 0u : (uint)i) });
        }
        public static string GetPropertyDescriptionInternal(uint id) => Label;
        public static BindingKind GetPropertyTypeInternal(uint id) => id == 0xf0102030u + ThrowKindFor
            ? throw new InvalidOperationException("fixture_kind_error") : new();
        public int PlayerData { get => throw new Exception("Do not query players"); set { SetterCalled = true; } }
    }
    public class PersonReference {
        public static bool Called;
        public static long GetPropertyCountInternal() { Called = true; return 0; }
    }
    public class EvilReference { }
}

namespace Il2CppInterop.Runtime.InteropTypes {
    public class Il2CppObjectBase { public IntPtr Pointer => new(1); }
}
namespace SI.Core {
    public class TypedValue {
        private readonly object? scalar; private readonly string type;
        public int GetCalls;
        public bool ThrowGet;
        public TypedValue(object? scalar, string type) { this.scalar = scalar; this.type = type; }
        public bool IsNull => scalar is null;
        public Il2CppSystem.Type DataType => new(type);
        public T Get<T>() { GetCalls++; if (ThrowGet) throw new InvalidOperationException("fixture_get_failure"); return (T)scalar!; }
        public Il2CppSystem.Object Get() { GetCalls++; return new() { Item = scalar }; }
        public static TypedValue Create<T>(T value) => new(value, typeof(T).FullName!);
        public string AsString() { GetCalls++; return (string)scalar!; }
    }
}
namespace SI.Bindable {
    public class Bindings {
        public struct Key { public ulong m_key; public string Path; public bool IsValid() => !string.IsNullOrEmpty(Path); }
        public enum SetFlags { None = 0, Default = 1 }
        public static int MaxGroupSize { get; set; } = 64;
        public int ActiveCalls, Roots;
        public bool ThrowBuild, ThrowDispose;
        public enum NodeFlags { Default = 0, Temporary = 1 }
        public enum GroupFlags { None = 0 }
        public delegate void GroupChangedCallback();
        public Key Create(ref Il2CppSystem.ReadOnlySpan<char> path, NodeFlags flags) {
            if (!path.Text.StartsWith("FMFaceProbe") || path.Text.Contains('.')) throw new Exception("Invalid private root");
            Roots++; return new() { Path = path.Text };
        }
        public void Set(ref Key key, SI.Core.TypedValue value, SetFlags flags) { if (!key.Path.StartsWith("FMFaceProbe")) throw new Exception("Cannot change existing UI"); }
        public void Remove(ref Key key) { if (!key.Path.StartsWith("FMFaceProbe")) throw new Exception("Cannot remove existing UI"); Roots--; }
        public GroupBuilder CreateGroup(Key key, GroupFlags flags) => new(this);
        public class GroupBuilder {
            private readonly Bindings owner; private int size;
            public GroupBuilder(Bindings owner) { this.owner = owner; }
            public GroupBuilder Add(int index, ref Key key, ref Il2CppSystem.ReadOnlySpan<char> path) { size++; return this; }
            public Group Build(GroupChangedCallback? callback) { if (owner.ThrowBuild) throw new Exception("fixture_build_failure"); return new(size, owner.ThrowDispose); }
        }
        public class Group {
            public int Count { get; }
            private readonly bool throwDispose;
            public Group(int count, bool throwDispose = false) { Count = count; this.throwDispose = throwDispose; }
            public bool IsDone => true;
            public SI.Core.TypedValue Get(int index) => new(null, "System.String");
            public void Dispose() { if (throwDispose) throw new Exception("fixture_dispose_failure"); }
        }
        public string GetPathDebug(ref Key key) => key.Path;
        public SI.Core.TypedValue Get(ref Key key) { ActiveCalls++; throw new Exception("Do not query data"); }
        public void SetInternal(ref Key key, SI.Core.TypedValue value, SetFlags flags) { ActiveCalls++; throw new Exception("Do not write data"); }
    }
}

namespace Il2CppInterop.Runtime.InteropTypes.Arrays {
    public class Il2CppStructArray<T> { public T[] Values; public Il2CppStructArray(T[] values) { Values = values; } }
}
namespace SI.Core {
    public struct DynamicNumber {
        public enum NumberKind : byte { SignedWhole, UnsignedWhole, FloatingPoint, Invalid }
        public enum FloatToWholeConversion { Truncate, Floor, Round, Ceil }
        private readonly long signed; private readonly ulong unsigned; private readonly double floating;
        public NumberKind Kind => initialized ? tag : NumberKind.Invalid;
        private readonly NumberKind tag; private readonly bool initialized;
        public DynamicNumber(long value) { signed = value; unsigned = 0; floating = 0; tag = NumberKind.SignedWhole; initialized = true; }
        public DynamicNumber(ulong value) { signed = 0; unsigned = value; floating = 0; tag = NumberKind.UnsignedWhole; initialized = true; }
        public DynamicNumber(double value) { signed = 0; unsigned = 0; floating = value; tag = NumberKind.FloatingPoint; initialized = true; }
        public long GetLong(FloatToWholeConversion mode) => Kind == NumberKind.SignedWhole ? signed : throw new Exception("Wrong numeric access");
        public ulong GetULong(FloatToWholeConversion mode) => Kind == NumberKind.UnsignedWhole ? unsigned : throw new Exception("Wrong numeric access");
        public double GetDouble() => Kind == NumberKind.FloatingPoint ? floating : throw new Exception("Wrong numeric access");
    }
}
public sealed class FakeProbeRuntime : ITeamProbeRuntime {
    public bool Ready => true;
    public bool Stall, WrongChildren;
    public List<int> Started = new(); public int Closed;
    public void Begin(int teamIndex) { Started.Add(teamIndex); }
    public TeamProbeResult? Poll() => Stall ? null : new() { values = new() {
        ["TeamContainer.HighestLevelYouthTeam"] = new() { record_table = "Team", record_index = WrongChildren ? 999 : 28346 },
        ["TeamContainer.SecondHighestLevelYouthTeam"] = new() { record_table = "Team", record_index = WrongChildren ? 998 : 28347 }
    } };
    public void Close() { Closed++; }
}
