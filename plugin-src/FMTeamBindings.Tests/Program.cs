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

namespace Il2CppSystem {
    public class ValueType { }
    public class Type { private readonly string name; public Type(string name = "System.Int32") { this.name = name; } public string FullName => name; }
    public class Object : Il2CppInterop.Runtime.InteropTypes.Il2CppObjectBase { }
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
    public class TeamReference {
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
    public class Il2CppObjectBase { public IntPtr Pointer => IntPtr.Zero; }
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
        public Il2CppSystem.Object Get() { GetCalls++; throw new Exception("Record not requested in this test"); }
        public string AsString() { GetCalls++; return (string)scalar!; }
    }
}
namespace SI.Bindable {
    public class Bindings {
        public struct Key { public string Path; }
        public enum SetFlags { None = 0 }
        public int ActiveCalls;
        public string GetPathDebug(ref Key key) => key.Path;
        public SI.Core.TypedValue Get(ref Key key) { ActiveCalls++; throw new Exception("Do not query data"); }
        public void SetInternal(ref Key key, SI.Core.TypedValue value, SetFlags flags) { ActiveCalls++; throw new Exception("Do not write data"); }
    }
}
