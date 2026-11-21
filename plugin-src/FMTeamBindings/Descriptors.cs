using System.Reflection;

namespace FMTeamBindings;

// Only schema descriptors are called. Never opens a data channel, queries a person,
// changes UI context, writes a game property, or infers a squad from a list slot.
public static class Descriptors
{
    public const int Limit = 8192;
    private const BindingFlags Static = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static | BindingFlags.DeclaredOnly;
    public static readonly string[] References = {
        "FM.UI.TeamReference", "FM.UI.TeamSquadReference", "FM.UI.PersonReference",
        "FM.UI.ClubReference", "FM.UI.SquadOverviewPlayerReference"
    };
    public static readonly string[] SupportingTypes = {
        "FM.UI.DatabaseRecordReference", "FM.UI.DatabaseTableType",
        "SI.Bindable.Reference.Core.PropertyID", "SI.Bindable.Reference.Core.ReferenceID",
        "SI.Bindable.Reference.Core.ContextID", "SI.Bindable.Reference.Core.Kind",
        "SI.Bindable.Reference.Core.BindingKind", "SI.Bindable.Reference.Core.PropertyIDInfo",
        "SI.Bindable.Reference.Core.ReferenceIDInfo", "SI.Bindable.Reference.Core.IdentifierUtils",
        "SI.Bindable.Reference.Core.IdentifierInfo", "SI.Bindable.Reference.Core.IDataReference",
        "SI.Bindable.DynamicReference", "SI.Bindable.PropertyHandler", "SI.Bindable.Bindings",
        "SI.Bindable.ReferenceUtils", "SI.Bindable.Bindings+Property", "SI.Bindable.Bindings+ContextMapping",
        "SI.Bindable.Bindings+ContextInfo", "SI.Bindable.PropertyHandler+GetContext", "SI.Bindable.PropertyHandler+OpenChannel",
        "SI.Core.TypedValue", "SI.Core.ReferenceTypedValue", "SI.Core.DynamicNumber",
        "SI.Core.DynamicNumber+NumberKind", "SI.Core.DynamicNumber+FloatToWholeConversion",
        "SI.Interop.InteropReference", "SI.Interop.IInteropReferenceFactory", "SI.Interop.InteropUtils",
        "FM.GamePlugin.GameRecordSerialisation", "FM.GamePlugin.UIRecordUtils", "FM.GamePlugin.UiRecordID",
        "FM.GamePlugin.GameInteropSubsystem", "FM.GamePlugin.GamePlugin", "FM.GamePlugin.IGamePlugin"
    };
    private static MethodInfo Exact(Type type, string name, Type result, params Type[] arguments)
        => Exact(type, Static, name, result, arguments);
    private static MethodInfo Exact(Type type, BindingFlags flags, string name, Type result, params Type[] arguments)
    {
        var found = type.GetMethods(flags).Where(m => m.Name == name && !m.ContainsGenericParameters
            && m.ReturnType == result && m.GetParameters().Select(p => p.ParameterType).SequenceEqual(arguments)).ToArray();
        return found.Length == 1 ? found[0] : throw new MissingMethodException(type.FullName, name);
    }
    private const BindingFlags Instance = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance;
    private static Type ReturnType(Type type, string name, string expected)
    {
        var method = type.GetMethods(Instance).Single(m => m.Name == name && !m.ContainsGenericParameters
            && m.GetParameters().Length == 0 && m.ReturnType.FullName == expected);
        return method.ReturnType;
    }
    private static uint Identifier(object value)
    {
        var type = value.GetType();
        if (type.FullName is not ("SI.Bindable.Reference.Core.PropertyID" or "SI.Bindable.Reference.Core.ReferenceID"))
            throw new InvalidOperationException("unexpected_identifier");
        var field = type.GetField("id", BindingFlags.Instance | BindingFlags.Public | BindingFlags.DeclaredOnly);
        if (field?.FieldType == typeof(uint)) return (uint)field.GetValue(value)!;
        return (uint)Exact(type, Instance, "get_ID", typeof(uint)).Invoke(value, null)!;
    }
    private static string Bounded(string? value)
    {
        if (value?.Length > 2048) throw new InvalidOperationException("descriptor_text_too_long");
        return value ?? "";
    }
    public static SchemaResult Read(Type type, Type list, Action? onDescriptorCall = null)
    {
        var scan = new Scan(type, list, onDescriptorCall);
        while (!scan.Done) scan.Step();
        return scan.Result;
    }
    public sealed class Scan
    {
        public SchemaResult Result { get; }
        public bool Done { get; private set; }
        private readonly Type type, list;
        private readonly Action? before;
        private MethodInfo? countMethod, properties, description, binding, getCount, item, getName;
        private MethodInfo? getKind, getReference, getType, getIsList;
        private object? values;
        private int next;
        private readonly HashSet<uint> seen = new();
        public Scan(Type type, Type list, Action? onDescriptorCall = null)
        {
            this.type = type; this.list = list; before = onDescriptorCall;
            Result = new() { reference = type.FullName ?? "" };
            try { Prepare(); }
            catch (Exception e) { Fail("signature", e); }
        }
        private object? Call(MethodInfo method, object? target, params object[] arguments)
        { before?.Invoke(); return method.Invoke(target, arguments); }
        private void Prepare()
        {
            if (!References.Contains(type.FullName)) throw new InvalidOperationException("reference_not_allowlisted");
            if (!list.IsGenericType || list.GetGenericArguments().Length != 1
                || list.GetGenericArguments()[0].FullName != "SI.Bindable.Reference.Core.PropertyID")
                throw new InvalidOperationException("unexpected_property_list");
            countMethod = Exact(type, "GetPropertyCountInternal", typeof(int));
            properties = Exact(type, "GetPropertiesInternal", typeof(void), list);
            description = Exact(type, "GetPropertyDescriptionInternal", typeof(string), typeof(uint));
            binding = type.GetMethods(Static).Single(m => m.Name == "GetPropertyTypeInternal" && !m.ContainsGenericParameters
                && m.ReturnType.FullName == "SI.Bindable.Reference.Core.BindingKind"
                && m.GetParameters().Select(p => p.ParameterType).SequenceEqual(new[] { typeof(uint) }));
            // Actual game metadata: BindingKind is an IL2CPP value wrapper, not an enum.
            var kindType = ReturnType(binding.ReturnType, "get_Kind", "SI.Bindable.Reference.Core.Kind");
            if (!kindType.IsEnum) throw new InvalidOperationException("kind_member_not_enum");
            getKind = Exact(binding.ReturnType, Instance, "get_Kind", kindType);
            getReference = Exact(binding.ReturnType, Instance, "get_Reference",
                ReturnType(binding.ReturnType, "get_Reference", "SI.Bindable.Reference.Core.ReferenceID"));
            getType = Exact(binding.ReturnType, Instance, "get_Type",
                ReturnType(binding.ReturnType, "get_Type", "Il2CppSystem.Type"));
            getIsList = Exact(binding.ReturnType, Instance, "get_IsList", typeof(bool));
            getCount = Exact(list, Instance, "get_Count", typeof(int));
            item = Exact(list, Instance, "get_Item", list.GetGenericArguments()[0], typeof(int));
            if (list.GetConstructor(Type.EmptyTypes) is null) throw new InvalidOperationException("property_list_constructor_missing");
            var idType = list.GetGenericArguments()[0];
            // Confirmed IdentifierUtils.GetName<TIdentifier>(TIdentifier) describes a
            // schema identifier; retain it independently of the optional description.
            try
            {
                getName = idType.Assembly.GetType("SI.Bindable.Reference.Core.IdentifierUtils", true)!
                    .GetMethods(Static).Single(m => m.Name == "GetName" && m.IsGenericMethodDefinition
                        && m.GetGenericArguments().Length == 1 && m.ReturnType == typeof(string)
                        && m.GetParameters().Length == 1 && m.GetParameters()[0].ParameterType.IsGenericParameter)
                    .MakeGenericMethod(idType);
            }
            catch { getName = null; }
            var field = idType.GetField("id", BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly);
            if (field?.FieldType != typeof(uint)) Exact(idType, Instance, "get_ID", typeof(uint));
        }
        private void Start()
        {
            Result.declared_count = (int)Call(countMethod!, null)!;
            if (Result.declared_count < 0 || Result.declared_count > Limit)
                throw new InvalidOperationException("property_count_out_of_bounds");
            values = Activator.CreateInstance(list)!;
            Call(properties!, null, values);
            Result.count = (int)Call(getCount!, values)!;
            if (Result.count != Result.declared_count || Result.count < 0 || Result.count > Limit)
                throw new InvalidOperationException("property_count_mismatch");
        }
        public void Step(int budget = 32)
        {
            if (Done) return;
            if (budget < 1 || budget > 64) throw new ArgumentOutOfRangeException(nameof(budget));
            try
            {
                if (values is null) Start();
                var clock = System.Diagnostics.Stopwatch.StartNew();
                for (var i = 0; i < budget && next < Result.count; i++)
                {
                    var row = new PropertyEntry();
                    Result.properties.Add(row);
                    try
                    {
                        var identifier = Call(item!, values, next)!;
                        row.id = Identifier(identifier);
                        if (!seen.Add(row.id.Value)) throw new InvalidOperationException("duplicate_property_id");
                        try
                        {
                            if (getName is null) throw new InvalidOperationException("identifier_name_signature_unavailable");
                            row.name = Bounded((string?)Call(getName, null, identifier));
                        }
                        catch (Exception e) { row.errors.Add(Error("property_name", e)); }
                        try { row.description = Bounded((string?)Call(description!, null, row.id.Value)); }
                        catch (Exception e) { row.errors.Add(Error("description", e)); }
                        try { ReadKind(row); }
                        catch (Exception e) { row.errors.Add(Error("binding_kind", e)); }
                    }
                    catch (Exception e) { row.errors.Add(Error("property_id", e)); }
                    next++; Result.scanned_count = next;
                    if (clock.ElapsedMilliseconds >= 5) break;
                }
                if (next == Result.count) { Done = true; Result.complete = true; }
            }
            catch (Exception e) { Fail("list", e); }
        }
        private void ReadKind(PropertyEntry row)
        {
            var bindingValue = Call(binding!, null, row.id!.Value) ?? throw new InvalidOperationException("null_binding_kind");
            var kind = Call(getKind!, bindingValue)!;
            row.kind = Enum.GetName(kind.GetType(), kind); row.kind_value = Convert.ToInt64(kind);
            row.is_list = (bool)Call(getIsList!, bindingValue)!;
            if (row.kind == "Reference")
            {
                var reference = Call(getReference!, bindingValue)!;
                row.reference_id = Identifier(reference);
                // ReferenceID.GetInfo().Name reads the schema registry, not a team/player.
                var infoMethod = Exact(reference.GetType(), Instance, "GetInfo",
                    ReturnType(reference.GetType(), "GetInfo", "SI.Bindable.Reference.Core.ReferenceIDInfo"));
                var info = Call(infoMethod, reference) ?? throw new InvalidOperationException("reference_info_missing");
                row.reference_name = Bounded((string?)Call(Exact(info.GetType(), Instance, "get_Name", typeof(string)), info));
            }
            else if (row.kind == "Value")
            {
                var valueType = Call(getType!, bindingValue);
                if (valueType is not null)
                    row.value_type = Bounded((string?)Call(Exact(valueType.GetType(), Instance, "get_FullName", typeof(string)), valueType));
            }
        }
        private void Fail(string stage, Exception e) { Result.errors.Add(Error(stage, e)); Done = true; }
    }
    private static ScanError Error(string stage, Exception e)
    {
        var cause = e.GetBaseException();
        return new() { stage = stage, error = cause.GetType().Name,
            code = cause is InvalidOperationException && cause.Message.Length <= 80
                && cause.Message.All(c => (c is >= 'a' and <= 'z' or >= 'A' and <= 'Z' or >= '0' and <= '9') || c == '_') ? cause.Message : "descriptor_unavailable" };
    }
    public static object Shape(Type type)
    {
        const BindingFlags own = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static | BindingFlags.Instance | BindingFlags.DeclaredOnly;
        var methods = type.GetMethods(own).Where(m => !m.Name.StartsWith("Native", StringComparison.Ordinal)).ToArray();
        return new { name = type.FullName, assembly = type.Assembly.GetName().Name, base_type = type.BaseType?.FullName,
            is_enum = type.IsEnum, total_methods = methods.Length,
            constructors = type.GetConstructors(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance).Take(40)
                .Select(c => new { is_public = c.IsPublic, parameters = c.GetParameters().Select(p => new { name = p.Name, type = p.ParameterType.ToString() }).ToArray() }).ToArray(),
            methods = methods.Take(250).Select(m => new { name = m.Name, is_static = m.IsStatic,
                return_type = m.ReturnType.ToString(), parameters = m.GetParameters().Select(p => new { name = p.Name, type = p.ParameterType.ToString() }).ToArray() }).ToArray(),
            fields = type.GetFields(own).Where(f => !f.Name.StartsWith("Native", StringComparison.Ordinal)).Take(100)
                .Select(f => new { name = f.Name, type = f.FieldType.ToString(), is_static = f.IsStatic,
                    constant = type.IsEnum && f.IsLiteral ? f.GetRawConstantValue() : null }).ToArray(),
            properties = type.GetProperties(own).Take(100).Select(p => new { name = p.Name, type = p.PropertyType.ToString() }).ToArray() };
    }
}

public sealed class SchemaResult
{
    public string reference { get; set; } = "";
    public int? declared_count { get; set; }
    public int? count { get; set; }
    public int scanned_count { get; set; }
    public bool complete { get; set; }
    public List<PropertyEntry> properties { get; } = new();
    public List<ScanError> errors { get; } = new();
    public bool HasErrors => errors.Count > 0 || properties.Any(p => p.errors.Count > 0);
}
public sealed class PropertyEntry
{
    public uint? id { get; set; }
    public string name { get; set; } = "";
    public string description { get; set; } = "";
    public string? kind { get; set; }
    public long? kind_value { get; set; }
    public bool? is_list { get; set; }
    public uint? reference_id { get; set; }
    public string? reference_name { get; set; }
    public string? value_type { get; set; }
    public List<ScanError> errors { get; } = new();
}
public sealed class ScanError
{
    public string stage { get; set; } = "";
    public string error { get; set; } = "";
    public string code { get; set; } = "";
}
