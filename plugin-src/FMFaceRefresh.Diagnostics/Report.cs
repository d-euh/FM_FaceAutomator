using System.Reflection;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;
using System.Security.Cryptography;
using System.Text.RegularExpressions;

namespace FMFaceRefresh.Diagnostics;

public static class Report
{
    public const string ExpectedBuild = "26620374";
    private static readonly string[] Keywords = {
        "resource", "portrait", "texture", "graphic", "cache", "panelmanager",
        "continuemanager", "ticksubsystem", "enumeratelocal", "preferences"
    };

    public static Dictionary<string, object?> Collect(string gameRoot, string bepinexRoot, string? loaderVersion = null, string? loaderInformationalVersion = null)
    {
        var errors = new List<string>();
        var manifest = SteamBuild(gameRoot);
        var assemblies = new List<object>();
        var scanned = 0;
        var interop = Path.Combine(bepinexRoot, "interop");
        if (Directory.Exists(interop))
            foreach (var file in Directory.EnumerateFiles(interop, "*.dll").OrderBy(Path.GetFileName, StringComparer.Ordinal))
            {
                try
                {
                    var entry = ScanAssembly(file);
                    scanned++;
                    if (entry is not null) assemblies.Add(entry);
                }
                catch (Exception exception)
                {
                    errors.Add($"{Path.GetFileName(file)}: {exception.GetType().Name}");
                }
            }
        else errors.Add("BepInEx interop directory is missing.");

        var hashes = new Dictionary<string, string>();
        foreach (var relative in new[] { "fm.exe", "GameAssembly.dll", "game_plugin.dll", "fm_Data/Plugins/x86_64/game_plugin.dll" })
        {
            var file = Path.Combine(gameRoot, relative);
            if (!File.Exists(file)) continue;
            try
            {
                using var stream = File.OpenRead(file);
                using var sha256 = SHA256.Create();
                hashes[relative] = Convert.ToHexString(sha256.ComputeHash(stream)).ToLowerInvariant();
            }
            catch (Exception exception) { errors.Add($"{relative}: {exception.GetType().Name}"); }
        }
        return new Dictionary<string, object?> {
            ["schema_version"] = 1, ["plugin_version"] = "0.1.0", ["generated_at_utc"] = DateTime.UtcNow,
            ["mode"] = "metadata_only", ["refresh_available"] = false,
            ["expected_steam_build"] = ExpectedBuild, ["detected_steam_build"] = manifest,
            ["build_matches"] = manifest == ExpectedBuild, ["loader_assembly_version"] = loaderVersion,
            ["loader_informational_version"] = loaderInformationalVersion,
            ["scanned_assemblies"] = scanned, ["candidate_assemblies"] = assemblies,
            ["game_file_sha256"] = hashes, ["errors"] = errors,
            ["notice"] = "No game methods were invoked. Finding a method does not establish compatibility or successful live refresh."
        };
    }

    public static string? SteamBuild(string gameRoot)
    {
        var game = Path.GetFullPath(gameRoot).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        var steamapps = Directory.GetParent(game)?.Parent?.FullName;
        if (steamapps is null || !Directory.Exists(steamapps)) return null;
        foreach (var file in Directory.EnumerateFiles(steamapps, "appmanifest_*.acf"))
        {
            try
            {
                var text = File.ReadAllText(file);
                var directory = Regex.Match(text, "\"installdir\"\\s+\"([^\"]+)\"").Groups[1].Value;
                if (directory.Length == 0) continue;
                var installed = Path.GetFullPath(Path.Combine(steamapps, "common", directory));
                if (string.Equals(installed, game, OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal))
                    return Regex.Match(text, "\"buildid\"\\s+\"(\\d+)\"").Groups[1].Value;
            }
            catch (IOException) { }
            catch (UnauthorizedAccessException) { }
        }
        return null;
    }

    public static object? ScanAssembly(string file)
    {
        // Inspect PE metadata directly; do not load interop assemblies or run static constructors.
        using var stream = File.OpenRead(file);
        using var pe = new PEReader(stream);
        if (!pe.HasMetadata) return null;
        var reader = pe.GetMetadataReader();
        var provider = new SignatureNames();
        var types = new List<object>();
        foreach (var handle in reader.TypeDefinitions)
        {
            var definition = reader.GetTypeDefinition(handle);
            var ns = reader.GetString(definition.Namespace);
            var name = reader.GetString(definition.Name);
            var fullName = ns + "." + name;
            if (!((ns.StartsWith("SI.") || ns.StartsWith("FM.")) && Keywords.Any(k => name.Contains(k, StringComparison.OrdinalIgnoreCase)))
                && fullName != "UnityEngine.Resources") continue;
            var methods = new List<object>();
            foreach (var methodHandle in definition.GetMethods())
            {
                var method = reader.GetMethodDefinition(methodHandle);
                var signature = method.DecodeSignature(provider, (object?)null);
                methods.Add(new {
                    name = reader.GetString(method.Name), token = MetadataTokens.GetToken(methodHandle),
                    is_static = (method.Attributes & MethodAttributes.Static) != 0,
                    return_type = signature.ReturnType, parameters = signature.ParameterTypes.ToArray(),
                    parameter_names = method.GetParameters().Select(p => reader.GetParameter(p))
                        .Where(p => p.SequenceNumber > 0).OrderBy(p => p.SequenceNumber).Select(p => reader.GetString(p.Name)).ToArray()
                });
            }
            var fields = definition.GetFields().Select(h => reader.GetFieldDefinition(h)).Select(f => new {
                name = reader.GetString(f.Name), type = f.DecodeSignature(provider, (object?)null),
                is_static = (f.Attributes & FieldAttributes.Static) != 0
            }).ToArray();
            types.Add(new { name = fullName, methods, fields });
        }
        return types.Count == 0 ? null : new { file = Path.GetFileName(file), module_id = reader.GetGuid(reader.GetModuleDefinition().Mvid), types };
    }
}

internal sealed class SignatureNames : ISignatureTypeProvider<string, object?>
{
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
    { var type = reader.GetTypeDefinition(handle); return reader.GetString(type.Namespace) + "." + reader.GetString(type.Name); }
    public string GetTypeFromReference(MetadataReader reader, TypeReferenceHandle handle, byte kind)
    { var type = reader.GetTypeReference(handle); return reader.GetString(type.Namespace) + "." + reader.GetString(type.Name); }
    public string GetTypeFromSpecification(MetadataReader reader, object? context, TypeSpecificationHandle handle, byte kind)
        => reader.GetTypeSpecification(handle).DecodeSignature(this, context);
}
