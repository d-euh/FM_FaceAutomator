using FMTeamMetadata;
using System.Text.Json;

void Check(bool condition, string reason) { if (!condition) throw new Exception(reason); }
var folder = Path.Combine(Path.GetTempPath(), "fm-team-metadata-" + Guid.NewGuid().ToString("N"));
try
{
    Directory.CreateDirectory(folder);
    File.Copy(typeof(MetadataReport).Assembly.Location, Path.Combine(folder, "FM.Fixture.dll"));
    File.WriteAllText(Path.Combine(folder, "FM.Broken.dll"), "not a DLL");
    File.WriteAllText(Path.Combine(folder, "Other.dll"), "must not scan unrelated files");
    var original = File.ReadAllBytes(Path.Combine(folder, "FM.Fixture.dll"));
    var report = MetadataReport.Collect(folder, "26620374");
    var bytes = MetadataReport.SerializeBounded(report);
    var text = System.Text.Encoding.UTF8.GetString(bytes);
    using var document = JsonDocument.Parse(bytes);
    var root = document.RootElement;
    Check(root.GetProperty("mode").GetString() == "metadata_only", "Must be metadata-only");
    Check(!root.GetProperty("game_methods_invoked").GetBoolean(), "Must never claim game execution");
    Check(root.GetProperty("errors").GetArrayLength() == 1, "Corrupt game assembly must be reported independently");
    Check(root.GetProperty("scanned_assemblies").GetInt32() == 1, "Must skip unrelated files");
    var assembly = root.GetProperty("assemblies")[0];
    Check(assembly.GetProperty("module_id").GetString()?.Length == 36, "Need module fingerprint");
    var types = assembly.GetProperty("candidates").EnumerateArray().ToArray();
    Check(types.Any(t => t.GetProperty("name").GetString() == "SI.Data.PersonReference"), "Need player-to-team accessors even without Team in the type name");
    var team = types.Single(t => t.GetProperty("name").GetString() == "SI.Data.ClubTeam");
    var getter = team.GetProperty("methods").EnumerateArray().Single(m => m.GetProperty("name").GetString() == "get_Kind");
    Check(getter.GetProperty("return_type").GetString() == "SI.Data.ClubTeam+TeamKind", "Nested enum name must keep its owner");
    Check(!team.GetProperty("methods").EnumerateArray().Any(m => m.GetProperty("name").GetString() == "set_Kind"), "Must omit write methods");
    Check(!team.GetProperty("fields").EnumerateArray().Any(f => f.GetProperty("name").GetString()!.StartsWith("Native")), "Must omit native thunk boilerplate");
    Check(team.GetProperty("properties").EnumerateArray().Any(p => p.GetProperty("name").GetString() == "Kind"), "Property signature missing");
    var kind = types.Single(t => t.GetProperty("name").GetString() == "SI.Data.ClubTeam+TeamKind");
    Check(kind.GetProperty("is_enum").GetBoolean(), "Enum not detected");
    var values = kind.GetProperty("fields").EnumerateArray().Where(f => f.GetProperty("constant").ValueKind != JsonValueKind.Null)
        .ToDictionary(f => f.GetProperty("name").GetString()!, f => f.GetProperty("constant").GetInt32());
    Check(values["Unknown"] == -1 && values["Senior"] == 7 && values["Under21"] == 13 && values["Under18"] == 42,
        "Read enum constants rather than guessing slot meanings");
    Check(root.GetProperty("tool_version").GetString() == "0.2.0", "Need focus-capable tool version");
    var number = types.Single(t => t.GetProperty("name").GetString() == "SI.Core.DynamicNumber");
    Check(number.GetProperty("focused_api").GetBoolean(), "DynamicNumber must bypass team-name filtering");
    var numberMethods = number.GetProperty("methods").EnumerateArray().ToArray();
    Check(numberMethods.Any(m => m.GetProperty("name").GetString() == ".ctor" && m.GetProperty("parameters")[0].GetString() == "IntPtr"),
        "Need constructor signatures without invoking them");
    Check(numberMethods.Any(m => m.GetProperty("name").GetString() == "op_Explicit"), "Need numeric conversion signatures");
    var generic = numberMethods.Single(m => m.GetProperty("name").GetString() == "As").GetProperty("generic_parameters")[0];
    Check(generic.GetProperty("attributes").GetString()!.Contains("NotNullableValueTypeConstraint"), "Must preserve value-type generic constraints");
    Check(numberMethods.Any(m => m.GetProperty("name").GetString() == "set_Value"), "Focused signatures include setters as metadata only");
    Check(!numberMethods.Any(m => m.GetProperty("name").GetString() == ".cctor"), "No need to include static initialisers");
    var channel = types.Single(t => t.GetProperty("name").GetString() == "SI.Bindable.IDataHandler");
    Check(channel.GetProperty("is_interface").GetBoolean(), "Need bridge interface type kind");
    Check(channel.GetProperty("methods").EnumerateArray().Any(m => m.GetProperty("name").GetString() == "Open"), "Need channel signatures, never execution");
    Check(!text.Contains("SECRET_CONSTANT_VALUE") && !text.Contains(folder), "Must omit literal strings and installation paths");
    Check(File.ReadAllBytes(Path.Combine(folder, "FM.Fixture.dll")).SequenceEqual(original), "Must not alter source files");
    Check(bytes.Length < MetadataReport.MaxBytes, "Report must fit attachment limit");
    var failed = false;
    try { MetadataReport.SerializeBounded(report, 16); } catch (InvalidDataException) { failed = true; }
    Check(failed, "Must fail instead of writing an oversized report");
    Console.WriteLine("PASS: static-only scanning, focused numeric/bridge interfaces, constructor/conversion signatures, generic constraints, enum values, corrupt DLL isolation, no literals/paths and bounded immutable inputs.");
}
finally { Directory.Delete(folder, true); }

namespace SI.Data
{
    public class PersonReference
    {
        public ClubTeam CurrentTeam => throw new InvalidOperationException("Never execute a player getter");
    }
    public class ClubTeam
    {
        static ClubTeam() => throw new InvalidOperationException("Game static constructors must never execute");
        public enum TeamKind : sbyte { Unknown = -1, Senior = 7, Under21 = 13, Under18 = 42 }
        public TeamKind Kind { get; set; }
        public int TeamId;
        public static IntPtr NativeMethodInfoPtr_GetSecret;
        public const string SecretLiteral = "SECRET_CONSTANT_VALUE";
        public ClubTeam? FindTeam(int teamId) => throw new InvalidOperationException("Game methods must never execute");
    }
}

namespace SI.Core
{
    public class DynamicNumber
    {
        static DynamicNumber() => throw new Exception("Must not initialise game wrappers");
        public DynamicNumber(IntPtr pointer) => throw new Exception("Must not call native constructors");
        public long Value { get => throw new Exception("Must not read runtime values"); set => throw new Exception("Must not write runtime values"); }
        public T As<T>() where T : struct => throw new Exception("Must not convert native values");
        public static explicit operator long(DynamicNumber value) => throw new Exception("Must not invoke conversions");
    }
}
namespace SI.Bindable
{
    public interface IDataHandler { void Open(int key); }
}
