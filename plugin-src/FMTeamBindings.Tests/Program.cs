using System.Text.Json;
using FMTeamBindings;

void Check(bool condition, string reason) { if (!condition) throw new Exception(reason); }
var type = typeof(FM.UI.TeamReference);
var list = typeof(List<SI.Bindable.Reference.Core.PropertyID>);
var calls = 0;
var result = JsonSerializer.SerializeToElement(Descriptors.Read(type, list, () => calls++));
Check(calls == 4, "Must report descriptor call attempts accurately");
Check(result.GetProperty("properties")[0].GetProperty("id").GetUInt32() == 0xf0102030u, "Must read IDs, never enumerate an assumed numeric range");
Check(result.GetProperty("properties")[0].GetProperty("description").GetString() == "registered_team_kind", "Missing descriptor");
Check(result.GetProperty("properties")[0].GetProperty("kind_value").GetInt64() == 13, "Preserve explicit kind");
Check(!FM.UI.TeamReference.SetterCalled, "Must not write game data");
foreach (var count in new[] { -1, 1025 }) {
    FM.UI.TeamReference.Count = count;
    try { Descriptors.Read(type, list); throw new Exception("Invalid count accepted"); }
    catch (InvalidOperationException e) { Check(e.Message == "property_count_out_of_bounds", "Wrong bounds failure"); }
}
Check(FM.UI.TeamReference.FillCalls == 1, "Overflow must be rejected before allocating/filling a game list");
FM.UI.TeamReference.Count = 2;
try { Descriptors.Read(type, list); throw new Exception("Mismatch accepted"); }
catch (InvalidOperationException e) { Check(e.Message == "property_count_mismatch", "Wrong mismatch failure"); }
try { Descriptors.Read(typeof(FM.UI.EvilReference), list); throw new Exception("Unknown type accepted"); }
catch (InvalidOperationException e) { Check(e.Message == "reference_not_allowlisted", "Wrong allowlist failure"); }
FM.UI.TeamReference.Count = 1;
FM.UI.TeamReference.Label = new string('x', 2049);
try { Descriptors.Read(type, list); throw new Exception("Oversize accepted"); }
catch (InvalidOperationException e) { Check(e.Message == "property_description_too_long", "Wrong label failure"); }
try { Descriptors.Read(typeof(FM.UI.PersonReference), list); throw new Exception("Bad descriptor signature accepted"); }
catch (MissingMethodException) { }
Check(!FM.UI.PersonReference.Called, "Signature mismatch must fail before any native call");
var shape = JsonSerializer.SerializeToElement(Descriptors.Shape(type));
Check(shape.GetProperty("methods").GetArrayLength() > 0, "Need supporting signatures without invoking them");
Check(!FM.UI.TeamReference.SetterCalled, "Shape collection must not call getters/setters");
Console.WriteLine("PASS: allowlist, nonsequential IDs, explicit enum kind, count/size bounds, mismatch, no state writes.");

namespace SI.Bindable.Reference.Core {
    public struct PropertyID { public uint Value; }
    public enum BindingKind { Reference = 13 }
}
namespace FM.UI {
    public class TeamReference {
        public static int Count = 1, FillCalls;
        public static bool SetterCalled;
        public static string Label = "registered_team_kind";
        public static int GetPropertyCountInternal() => Count;
        public static void GetPropertiesInternal(List<SI.Bindable.Reference.Core.PropertyID> target) {
            FillCalls++; target.Add(new() { Value = 0xf0102030u });
        }
        public static string GetPropertyDescriptionInternal(uint id) => Label;
        public static SI.Bindable.Reference.Core.BindingKind GetPropertyTypeInternal(uint id) => SI.Bindable.Reference.Core.BindingKind.Reference;
        public int PlayerData { get => throw new Exception("Do not query players"); set { SetterCalled = true; } }
    }
    public class PersonReference {
        public static bool Called;
        public static long GetPropertyCountInternal() { Called = true; return 0; }
    }
    public class EvilReference { }
}
