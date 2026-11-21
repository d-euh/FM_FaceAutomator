using System.Reflection;
using Il2CppInterop.Runtime.InteropTypes;

namespace FMTeamBindings;

// Observes values that the game's UI already read/wrote. No OpenChannel, Set,
// SendEvent, Bindings.Get, or other active data query is invoked by this class.
public sealed class BindingObserver
{
    private const BindingFlags Instance = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance;
    private readonly Func<string, Type> resolve;
    private readonly DynamicNumbers numbers;
    private readonly FieldInfo bindingKey;
    private readonly Dictionary<ulong,string> ownerKeys = new();
    public object? BindingOwner { get; private set; }
    public int? HumanTeamIndex { get; private set; }
    private readonly MethodInfo pathDebug, dataType, isNull, getValue, getObject;
    private readonly Dictionary<string, MethodInfo> primitive = new();
    private readonly Dictionary<string, MethodInfo> fullNames = new();
    public MethodInfo Get { get; }
    public MethodInfo SetInternal { get; }
    public ValueObservations Values { get; } = new();
    public bool Dirty { get; set; }
    public long seen_events { get; private set; }
    public long inspected_events { get; private set; }
    public long skipped_for_frame_budget { get; private set; }
    public long read_errors { get; private set; }
    private bool inside;
    private int frameCalls, frame, ordinal, stride = 1;
    private readonly Dictionary<string, int> eventKinds = new();
    public IReadOnlyDictionary<string, int> event_counts => eventKinds;
    public static MethodInfo Method(Type type, string name, string result, params string[] arguments)
    {
        var methods = type.GetMethods(Instance).Where(m => !m.IsGenericMethodDefinition && m.Name == name
            && m.ReturnType.FullName == result
            && m.GetParameters().Select(p => p.ParameterType.FullName).SequenceEqual(arguments)).ToArray();
        return methods.Length == 1 ? methods[0] : throw new MissingMethodException(type.FullName, name);
    }
    public BindingObserver(Func<string, Type> resolve)
    {
        this.resolve = resolve;
        var bindings = resolve("SI.Bindable.Bindings");
        var value = resolve("SI.Core.TypedValue");
        bindingKey = resolve("SI.Bindable.Bindings+Key").GetField("m_key", BindingFlags.Public | BindingFlags.Instance)
            ?? throw new MissingFieldException("Bindings.Key.m_key");
        if (bindingKey.FieldType != typeof(ulong)) throw new InvalidOperationException("unexpected_binding_key");
        const string key = "SI.Bindable.Bindings+Key&";
        Get = Method(bindings, "Get", "SI.Core.TypedValue", key);
        SetInternal = Method(bindings, "SetInternal", "System.Void", key, "SI.Core.TypedValue", "SI.Bindable.Bindings+SetFlags");
        pathDebug = Method(bindings, "GetPathDebug", "System.String", key);
        dataType = Method(value, "get_DataType", "Il2CppSystem.Type");
        isNull = Method(value, "get_IsNull", "System.Boolean");
        getObject = Method(value, "Get", "Il2CppSystem.Object");
        getValue = value.GetMethods(Instance).Single(m => m.Name == "Get" && m.IsGenericMethodDefinition
            && m.GetGenericArguments().Length == 1 && m.GetParameters().Length == 0 && m.ReturnType.IsGenericParameter);
        foreach (var type in new[] { typeof(bool), typeof(sbyte), typeof(byte), typeof(short), typeof(ushort),
                                    typeof(int), typeof(uint), typeof(long), typeof(ulong), typeof(float), typeof(double) })
        {
            try { primitive[type.FullName!] = getValue.MakeGenericMethod(type); }
            catch (ArgumentException) { /* Unsupported generic instantiations are reported as opaque values. */ }
        }
        primitive["System.String"] = Method(value, "AsString", "System.String");
        numbers = new DynamicNumbers(resolve("SI.Core.DynamicNumber"), getValue);
    }
    public void NextFrame()
    {
        stride = Math.Max(1, (int)Math.Ceiling(ordinal / 96.0));
        frameCalls = 0; ordinal = 0; frame = (frame + 1) % 1000000;
    }
    public void Observe(object bindings, object key, object typedValue, string source, double elapsed, bool capture = true, bool discover = true)
    {
        if (inside) return;
        seen_events++;
        var rawKey = (ulong)bindingKey.GetValue(key)!;
        if (!capture && ownerKeys.TryGetValue(rawKey,out var ownerPath))
        {
            inside = true;
            try { UpdateOwner(bindings,rawKey,ownerPath,DecodeSupplied(typedValue)); }
            catch { read_errors++; }
            finally { inside = false; }
            return;
        }
        if (!capture && !discover) return;
        if (!eventKinds.ContainsKey(source)) eventKinds[source] = 0;
        eventKinds[source]++;
        // Spread reads across the previous frame's event volume and rotate the
        // offset. A busy early UI section must not always consume the whole budget.
        ordinal++;
        if (frameCalls >= 128 || (ordinal + frame) % stride != 0) { skipped_for_frame_budget++; return; }
        frameCalls++; inside = true;
        try
        {
            var path = pathDebug.Invoke(bindings, new[] { key }) as string ?? "";
            inspected_events++;
            if (!ValueObservations.Relevant(path) || !capture && path is not ("Human.Team" or "game.GameCurrentManager.Team")) return;
            ObservedValue value;
            try { value = DecodeSupplied(typedValue); }
            catch (Exception e) { read_errors++; value = new() { error = e.GetBaseException().GetType().Name }; }
            UpdateOwner(bindings,rawKey,path,value);
            if (capture && Values.Add(source, path, value, elapsed)) Dirty = true;
        }
        catch { read_errors++; }
        finally { inside = false; }
    }
    private void UpdateOwner(object bindings, ulong key, string path, ObservedValue value)
    {
        if ((path is "Human.Team" or "game.GameCurrentManager.Team") && value.error is null && (value.record_table == "Team" || value.is_null))
        {
            BindingOwner = bindings; HumanTeamIndex = value.record_index;
            if (key != 0 && ownerKeys.Count < 128) ownerKeys[key] = path;
        }
    }
    private string TypeName(object type)
    {
        var key = type.GetType().FullName!;
        if (!fullNames.TryGetValue(key, out var method)) fullNames[key] = method = Method(type.GetType(), "get_FullName", "System.String");
        var name = method.Invoke(type, null) as string ?? "";
        return name.Length <= 256 ? name : throw new InvalidOperationException("type_name_too_long");
    }
    public static string? DisplayText(string value)
    {
        if (!value.StartsWith("\u0001", StringComparison.Ordinal)) return value.Length <= 256 ? value : value[..256];
        var start = value.LastIndexOf('\u0002');
        if (start < 0) return null;
        var end = value.IndexOf('\u0001', start + 1);
        if (end < 0 || end - start - 1 > 256) return null;
        return value.Substring(start + 1, end - start - 1);
    }
    public ObservedValue DecodeSupplied(object value)
    {
        var result = new ObservedValue { is_null = isNull.Invoke(value, null) is true };
        if (result.is_null) return result;
        var type = dataType.Invoke(value, null) ?? throw new InvalidOperationException("data_type_missing");
        result.data_type = TypeName(type);
        try
        {
            if (result.data_type == "SI.Core.DynamicNumber") numbers.Read(value, result);
            else if (result.data_type == "SI.Bindable.NullReference") result.is_null = true;
            else if (primitive.TryGetValue(result.data_type, out var method))
            {
                var scalar = method.Invoke(value, null);
                if (scalar is string text)
                {
                    result.display_text = DisplayText(text);
                    if (text.Length > 256) scalar = text[..256];
                }
                if (scalar is float f && !float.IsFinite(f) || scalar is double d && !double.IsFinite(d))
                    result.error = "nonfinite_number";
                else result.scalar = scalar;
            }
            else if (result.data_type is "FM.UI.TeamReference" or "FM.UI.ClubReference" or "SI.Interop.InteropReference")
            {
                // DataType establishes the concrete wrapper before using its pointer.
                var boxed = getObject.Invoke(value, null);
                if (boxed is not Il2CppObjectBase native || native.Pointer == IntPtr.Zero) throw new InvalidOperationException("reference_wrapper_missing");
                var reference = Activator.CreateInstance(resolve(result.data_type), new object[] { native.Pointer })!;
                if (result.data_type == "SI.Interop.InteropReference")
                {
                    var identity = (string?)Method(reference.GetType(), "GetPersistentIdentity", "System.String").Invoke(reference, null);
                    result.persistent_identity = identity is { Length: <= 512 } ? identity : null;
                }
                else
                {
                    result.record_index = (int)Method(reference.GetType(), "get_Index", "System.Int32").Invoke(reference, null)!;
                    var table = Method(reference.GetType(), "get_Type", "FM.UI.DatabaseTableType").Invoke(reference, null)!;
                    if (!table.GetType().IsEnum) throw new InvalidOperationException("table_not_enum");
                    result.record_table = Enum.GetName(table.GetType(), table);
                }
            }
            else result.error = "unsupported_data_type"; // Never guess a boxed value's layout or stringify arbitrary objects.
        }
        catch (Exception e) { result.error = e.GetBaseException().GetType().Name; }
        return result;
    }
}
