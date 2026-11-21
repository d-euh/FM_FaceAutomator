using System.Reflection;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;
using System.Text.Json;

namespace FMTeamMetadata;

public sealed class TypeEntry
{
    public string name { get; set; } = "";
    public string base_type { get; set; } = "";
    public int token { get; set; }
    public bool is_enum { get; set; }
    public int total_methods { get; set; }
    public int total_fields { get; set; }
    public int total_properties { get; set; }
    public List<object> methods { get; set; } = new();
    public List<object> fields { get; set; } = new();
    public List<object> properties { get; set; } = new();
}

public sealed class AssemblyEntry
{
    public string file { get; set; } = "";
    public string module_id { get; set; } = "";
    public int candidate_count { get; set; }
    public int indexed_type_count { get; set; }
    public List<string> type_index { get; set; } = new();
    public List<TypeEntry> candidates { get; set; } = new();
    public List<string> errors { get; set; } = new();
}

public static class MetadataReport
{
    public const int MaxBytes = 24 * 1024 * 1024;
    private static readonly string[] Keywords = { "team", "squad", "youth", "reserve", "club" };

    private static bool GameFile(string name) => name.StartsWith("FM", StringComparison.OrdinalIgnoreCase)
        || name.StartsWith("SI.", StringComparison.OrdinalIgnoreCase);
    private static bool Candidate(string name) => Keywords.Any(k => name.Contains(k, StringComparison.OrdinalIgnoreCase))
        && !name.Contains("ReferenceRegistration", StringComparison.OrdinalIgnoreCase);
    private static bool Boilerplate(string name) => name.StartsWith("Native", StringComparison.Ordinal)
        || name.StartsWith("__", StringComparison.Ordinal);
    private static bool TeamAccessor(string name) =>
        (name.StartsWith("get_", StringComparison.Ordinal) || name.StartsWith("Get", StringComparison.Ordinal)
         || name.StartsWith("Find", StringComparison.Ordinal) || name.StartsWith("TryGet", StringComparison.Ordinal))
        && (name.Contains("team", StringComparison.OrdinalIgnoreCase) || name.Contains("squad", StringComparison.OrdinalIgnoreCase));
    private static int Priority(string name, bool isEnum)
    {
        if (isEnum) return 0;
        if (new[] { "TeamType", "SquadType", "TeamKind", "SquadKind", "TeamData", "TeamReference", "ClubTeam" }
            .Any(k => name.Contains(k, StringComparison.OrdinalIgnoreCase))) return 1;
        if (name.Contains("Youth", StringComparison.OrdinalIgnoreCase) || name.Contains("Reserve", StringComparison.OrdinalIgnoreCase)) return 2;
        return name.Contains("Team", StringComparison.OrdinalIgnoreCase) || name.Contains("Squad", StringComparison.OrdinalIgnoreCase) ? 3 : 4;
    }

    public static Dictionary<string, object?> Collect(string interop, string? build = null, Action<string>? progress = null)
    {
        var entries = new List<AssemblyEntry>();
        var errors = new List<string>();
        if (!Directory.Exists(interop)) throw new DirectoryNotFoundException("BepInEx interop directory is missing");
        var scanned = 0;
        foreach (var file in Directory.EnumerateFiles(interop, "*.dll").OrderBy(Path.GetFileName, StringComparer.Ordinal))
        {
            if (!GameFile(Path.GetFileName(file))) continue;
            progress?.Invoke(Path.GetFileName(file));
            try { entries.Add(Scan(file)); scanned++; }
            catch (Exception exc) { errors.Add(Path.GetFileName(file) + ":" + exc.GetType().Name); }
        }
        return new() {
            ["kind"] = "fm_team_metadata", ["schema_version"] = 1, ["tool_version"] = "0.1.0",
            ["mode"] = "metadata_only", ["game_methods_invoked"] = false,
            ["detected_steam_build"] = build, ["generated_at_utc"] = DateTime.UtcNow,
            ["scanned_assemblies"] = scanned, ["assemblies"] = entries, ["errors"] = errors,
            ["candidate_limit_per_assembly"] = 180, ["member_limit_per_type"] = 100,
            ["output_compacted"] = false,
            ["notice"] = "Static type names/signatures and numeric enum constants only. No game assemblies are loaded, no constructors/getters are executed, and no squad meanings or runtime player assignments are inferred. Counts record omitted entries."
        };
    }

    public static AssemblyEntry Scan(string file)
    {
        using var stream = File.OpenRead(file);
        using var pe = new PEReader(stream);
        if (!pe.HasMetadata) throw new BadImageFormatException("No managed metadata");
        var reader = pe.GetMetadataReader();
        var provider = new SignatureNames();
        var result = new AssemblyEntry { file = Path.GetFileName(file), module_id = reader.GetGuid(reader.GetModuleDefinition().Mvid).ToString() };
        var choices = new List<(TypeDefinitionHandle Handle, string Name, bool Enum, int Priority)>();
        foreach (var handle in reader.TypeDefinitions)
        {
            var type = reader.GetTypeDefinition(handle);
            var name = provider.GetTypeFromDefinition(reader, handle, 0);
            if (name == ".<Module>") continue;
            result.type_index.Add(name);
            var accessors = type.GetMethods().Select(m => reader.GetString(reader.GetMethodDefinition(m).Name)).Where(TeamAccessor).ToArray();
            if (Candidate(name) || accessors.Length > 0)
            {
                var isEnum = IsEnum(reader, type, provider);
                var priority = Priority(name, isEnum);
                if (accessors.Any(m => m.Contains("TeamType", StringComparison.OrdinalIgnoreCase)
                    || m.Contains("SquadType", StringComparison.OrdinalIgnoreCase))) priority = Math.Min(priority, 1);
                choices.Add((handle, name, isEnum, priority));
            }
        }
        result.indexed_type_count = result.type_index.Count;
        result.candidate_count = choices.Count;
        foreach (var (handle, name, isEnum, _) in choices.OrderBy(t => t.Priority).ThenBy(t => t.Name, StringComparer.Ordinal).Take(180))
        {
            try
            {
                var definition = reader.GetTypeDefinition(handle);
                var entry = new TypeEntry { name = name, token = MetadataTokens.GetToken(handle), is_enum = isEnum,
                    base_type = provider.TypeName(reader, definition.BaseType) };
                foreach (var fieldHandle in definition.GetFields().OrderBy(h => Candidate(reader.GetString(reader.GetFieldDefinition(h).Name)) ? 0 : 1))
                {
                    var field = reader.GetFieldDefinition(fieldHandle);
                    var fieldName = reader.GetString(field.Name);
                    if (Boilerplate(fieldName)) continue;
                    entry.total_fields++;
                    if (entry.fields.Count < 100 || isEnum)
                        entry.fields.Add(new { name = fieldName, type = field.DecodeSignature(provider, (object?)null),
                            is_static = (field.Attributes & FieldAttributes.Static) != 0,
                            constant = isEnum ? NumericConstant(reader, field.GetDefaultValue()) : null });
                }
                foreach (var methodHandle in definition.GetMethods().OrderBy(h => TeamAccessor(reader.GetString(reader.GetMethodDefinition(h).Name)) ? 0 : 1))
                {
                    var method = reader.GetMethodDefinition(methodHandle);
                    var methodName = reader.GetString(method.Name);
                    // Read-like signatures only; this does not execute or certify any getter.
                    if (!(methodName.StartsWith("get_", StringComparison.Ordinal) || methodName.StartsWith("Get", StringComparison.Ordinal)
                        || methodName.StartsWith("Find", StringComparison.Ordinal) || methodName.StartsWith("TryGet", StringComparison.Ordinal))) continue;
                    entry.total_methods++;
                    if (entry.methods.Count >= 100) continue;
                    var signature = method.DecodeSignature(provider, (object?)null);
                    entry.methods.Add(new { name = methodName, token = MetadataTokens.GetToken(methodHandle),
                        is_static = (method.Attributes & MethodAttributes.Static) != 0,
                        return_type = signature.ReturnType, parameters = signature.ParameterTypes.ToArray(),
                        parameter_names = method.GetParameters().Select(p => reader.GetParameter(p)).Where(p => p.SequenceNumber > 0)
                            .OrderBy(p => p.SequenceNumber).Select(p => reader.GetString(p.Name)).ToArray() });
                }
                foreach (var propertyHandle in definition.GetProperties().OrderBy(h => Candidate(reader.GetString(reader.GetPropertyDefinition(h).Name)) ? 0 : 1))
                {
                    var property = reader.GetPropertyDefinition(propertyHandle);
                    var propertyName = reader.GetString(property.Name);
                    if (Boilerplate(propertyName)) continue;
                    entry.total_properties++;
                    if (entry.properties.Count >= 100) continue;
                    var signature = property.DecodeSignature(provider, (object?)null);
                    var accessors = property.GetAccessors();
                    entry.properties.Add(new { name = propertyName, type = signature.ReturnType,
                        parameters = signature.ParameterTypes.ToArray(), has_getter = !accessors.Getter.IsNil,
                        has_setter = !accessors.Setter.IsNil });
                }
                result.candidates.Add(entry);
            }
            catch (Exception exc) { result.errors.Add(name + ":" + exc.GetType().Name); }
        }
        return result;
    }

    private static bool IsEnum(MetadataReader reader, TypeDefinition type, SignatureNames provider)
        => provider.TypeName(reader, type.BaseType) is "System.Enum" or "Il2CppSystem.Enum";

    private static object? NumericConstant(MetadataReader reader, ConstantHandle handle)
    {
        if (handle.IsNil) return null;
        var constant = reader.GetConstant(handle);
        var blob = reader.GetBlobReader(constant.Value);
        return constant.TypeCode switch {
            ConstantTypeCode.SByte => blob.ReadSByte(), ConstantTypeCode.Byte => blob.ReadByte(),
            ConstantTypeCode.Int16 => blob.ReadInt16(), ConstantTypeCode.UInt16 => blob.ReadUInt16(),
            ConstantTypeCode.Int32 => blob.ReadInt32(), ConstantTypeCode.UInt32 => blob.ReadUInt32(),
            ConstantTypeCode.Int64 => blob.ReadInt64(), ConstantTypeCode.UInt64 => blob.ReadUInt64(),
            _ => null // Never extract embedded string constants or instance data.
        };
    }

    public static byte[] SerializeBounded(Dictionary<string, object?> report, int limit = MaxBytes)
    {
        var bytes = JsonSerializer.SerializeToUtf8Bytes(report);
        if (bytes.Length <= limit) return bytes;
        report["output_compacted"] = true;
        var assemblies = (List<AssemblyEntry>)report["assemblies"]!;
        foreach (var keep in new[] { 40, 15, 5 })
        {
            foreach (var assembly in assemblies)
            {
                assembly.type_index = assembly.type_index.Take(5000).ToList();
                foreach (var type in assembly.candidates)
                {
                    type.methods = type.methods.Take(keep).ToList();
                    type.properties = type.properties.Take(keep).ToList();
                    if (!type.is_enum) type.fields = type.fields.Take(keep).ToList();
                }
            }
            bytes = JsonSerializer.SerializeToUtf8Bytes(report);
            if (bytes.Length <= limit) return bytes;
        }
        throw new InvalidDataException("Metadata exceeds the report size limit even after compaction");
    }
}

internal sealed class SignatureNames : ISignatureTypeProvider<string, object?>
{
    public string TypeName(MetadataReader reader, EntityHandle handle) => handle.Kind switch {
        HandleKind.TypeDefinition => GetTypeFromDefinition(reader, (TypeDefinitionHandle)handle, 0),
        HandleKind.TypeReference => GetTypeFromReference(reader, (TypeReferenceHandle)handle, 0),
        HandleKind.TypeSpecification => GetTypeFromSpecification(reader, null, (TypeSpecificationHandle)handle, 0), _ => "" };
    public string GetArrayType(string element, ArrayShape shape) => element + "[" + new string(',', Math.Max(0, shape.Rank - 1)) + "]";
    public string GetByReferenceType(string element) => element + "&";
    public string GetFunctionPointerType(MethodSignature<string> signature) => "methodptr(" + string.Join(",", signature.ParameterTypes) + ")->" + signature.ReturnType;
    public string GetGenericInstantiation(string type, System.Collections.Immutable.ImmutableArray<string> args) => type + "<" + string.Join(",", args) + ">";
    public string GetGenericMethodParameter(object? context, int index) => "!!" + index;
    public string GetGenericTypeParameter(object? context, int index) => "!" + index;
    public string GetModifiedType(string modifier, string type, bool required) => type;
    public string GetPinnedType(string element) => element + " pinned";
    public string GetPointerType(string element) => element + "*";
    public string GetPrimitiveType(PrimitiveTypeCode code) => code.ToString();
    public string GetSZArrayType(string element) => element + "[]";
    public string GetTypeFromDefinition(MetadataReader reader, TypeDefinitionHandle handle, byte kind)
    {
        var type = reader.GetTypeDefinition(handle);
        var parent = type.GetDeclaringType();
        return parent.IsNil ? reader.GetString(type.Namespace) + "." + reader.GetString(type.Name)
            : GetTypeFromDefinition(reader, parent, kind) + "+" + reader.GetString(type.Name);
    }
    public string GetTypeFromReference(MetadataReader reader, TypeReferenceHandle handle, byte kind)
    {
        var type = reader.GetTypeReference(handle);
        return type.ResolutionScope.Kind == HandleKind.TypeReference
            ? GetTypeFromReference(reader, (TypeReferenceHandle)type.ResolutionScope, kind) + "+" + reader.GetString(type.Name)
            : reader.GetString(type.Namespace) + "." + reader.GetString(type.Name);
    }
    public string GetTypeFromSpecification(MetadataReader reader, object? context, TypeSpecificationHandle handle, byte kind)
        => reader.GetTypeSpecification(handle).DecodeSignature(this, context);
}
