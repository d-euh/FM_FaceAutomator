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

namespace Il2CppSystem {
    public class ValueType { }
    public class Type { public string FullName => "System.Int32"; }
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
