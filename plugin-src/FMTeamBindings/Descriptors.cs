using System.Reflection;

namespace FMTeamBindings;

// Only schema descriptors are called. Never opens a data channel, queries a person,
// changes UI context, writes a game property, or infers a squad from a list slot.
public static class Descriptors
{
    public const int Limit = 1024;
    private const BindingFlags Static = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static | BindingFlags.DeclaredOnly;
    public static readonly string[] References = {
        "FM.UI.TeamReference", "FM.UI.TeamSquadReference", "FM.UI.PersonReference",
        "FM.UI.ClubReference", "FM.UI.DatabaseRecordReference", "FM.UI.SquadOverviewPlayerReference"
    };
    public static readonly string[] SupportingTypes = {
        "SI.Bindable.Reference.Core.PropertyID", "SI.Bindable.Reference.Core.ReferenceID",
        "SI.Bindable.Reference.Core.ContextID", "SI.Bindable.Reference.Core.Kind",
        "SI.Bindable.Reference.Core.BindingKind", "SI.Bindable.Reference.Core.PropertyIDInfo",
        "SI.Bindable.Reference.Core.ReferenceIDInfo", "SI.Bindable.Reference.Core.IdentifierUtils",
        "SI.Bindable.Reference.Core.IdentifierInfo", "SI.Bindable.Reference.Core.IDataReference",
        "SI.Bindable.DynamicReference", "SI.Bindable.PropertyHandler", "SI.Bindable.Bindings",
        "SI.Bindable.ReferenceUtils", "SI.Bindable.Bindings+Property", "SI.Bindable.Bindings+ContextMapping",
        "SI.Bindable.Bindings+ContextInfo", "SI.Bindable.PropertyHandler+GetContext", "SI.Bindable.PropertyHandler+OpenChannel",
        "SI.Core.TypedValue", "SI.Core.ReferenceTypedValue",
        "SI.Interop.InteropReference", "SI.Interop.IInteropReferenceFactory", "SI.Interop.InteropUtils",
        "FM.GamePlugin.GameRecordSerialisation", "FM.GamePlugin.UIRecordUtils", "FM.GamePlugin.UiRecordID",
        "FM.GamePlugin.GameInteropSubsystem", "FM.GamePlugin.GamePlugin", "FM.GamePlugin.IGamePlugin"
    };
    private static MethodInfo Exact(Type type, string name, Type result, params Type[] arguments)
    {
        var found = type.GetMethods(Static).Where(m => m.Name == name && !m.ContainsGenericParameters
            && m.ReturnType == result && m.GetParameters().Select(p => p.ParameterType).SequenceEqual(arguments)).ToArray();
        return found.Length == 1 ? found[0] : throw new MissingMethodException(type.FullName, name);
    }
    public static object Read(Type type, Type list, Action? onDescriptorCall = null)
    {
        if (!References.Contains(type.FullName)) throw new InvalidOperationException("reference_not_allowlisted");
        // Validate every signature before making the first native descriptor call.
        if (!list.IsGenericType || list.GetGenericArguments().Length != 1
            || list.GetGenericArguments()[0].FullName != "SI.Bindable.Reference.Core.PropertyID")
            throw new InvalidOperationException("unexpected_property_list");
        var countMethod = Exact(type, "GetPropertyCountInternal", typeof(int));
        var properties = Exact(type, "GetPropertiesInternal", typeof(void), list);
        var description = Exact(type, "GetPropertyDescriptionInternal", typeof(string), typeof(uint));
        var kind = type.GetMethods(Static).Single(m => m.Name == "GetPropertyTypeInternal" && !m.ContainsGenericParameters
            && m.ReturnType.FullName == "SI.Bindable.Reference.Core.BindingKind"
            && m.GetParameters().Select(p => p.ParameterType).SequenceEqual(new[] { typeof(uint) }));
        var getCount = list.GetMethod("get_Count", Type.EmptyTypes);
        var item = list.GetMethod("get_Item", new[] { typeof(int) });
        var constructor = list.GetConstructor(Type.EmptyTypes);
        if (getCount?.ReturnType != typeof(int) || item?.ReturnType != list.GetGenericArguments()[0] || constructor is null)
            throw new InvalidOperationException("unexpected_property_list_accessors");
        var idType = list.GetGenericArguments()[0];
        // Il2Cpp value wrappers may expose their single UInt32 storage as a field
        // or a generated field getter. Ambiguity fails closed, without guessing offsets.
        var fields = idType.GetFields(BindingFlags.Instance | BindingFlags.Public | BindingFlags.DeclaredOnly)
            .Where(f => f.FieldType == typeof(uint)).ToArray();
        var getters = idType.GetMethods(BindingFlags.Instance | BindingFlags.Public | BindingFlags.DeclaredOnly)
            .Where(m => m.IsSpecialName && m.Name.StartsWith("get_", StringComparison.Ordinal)
                && m.ReturnType == typeof(uint) && m.GetParameters().Length == 0).ToArray();
        if (fields.Length != 1 && (fields.Length != 0 || getters.Length != 1))
            throw new InvalidOperationException("ambiguous_property_id_storage");
        onDescriptorCall?.Invoke();
        var declared = (int)countMethod.Invoke(null, null)!;
        if (declared < 0 || declared > Limit) throw new InvalidOperationException("property_count_out_of_bounds");
        var values = constructor.Invoke(null);
        onDescriptorCall?.Invoke();
        properties.Invoke(null, new[] { values });
        var count = (int)getCount.Invoke(values, null)!;
        if (count != declared || count > Limit) throw new InvalidOperationException("property_count_mismatch");
        var rows = new List<object>();
        var seen = new HashSet<uint>();
        for (int i = 0; i < count; i++)
        {
            var id = item.Invoke(values, new object[] { i })!;
            var raw = (uint)(fields.Length == 1 ? fields[0].GetValue(id)! : getters[0].Invoke(id, null)!);
            if (!seen.Add(raw)) throw new InvalidOperationException("duplicate_property_id");
            onDescriptorCall?.Invoke();
            var label = (string?)description.Invoke(null, new object[] { raw }) ?? "";
            if (label.Length > 2048) throw new InvalidOperationException("property_description_too_long");
            onDescriptorCall?.Invoke();
            var k = kind.Invoke(null, new object[] { raw })!;
            if (!k.GetType().IsEnum) throw new InvalidOperationException("binding_kind_not_enum");
            rows.Add(new { id = raw, description = label, kind = Enum.GetName(k.GetType(), k), kind_value = Convert.ToInt64(k) });
        }
        return new { reference = type.FullName, count, properties = rows };
    }
    public static object Shape(Type type)
    {
        const BindingFlags own = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static | BindingFlags.Instance | BindingFlags.DeclaredOnly;
        var methods = type.GetMethods(own).Where(m => !m.Name.StartsWith("Native", StringComparison.Ordinal)).ToArray();
        return new { name = type.FullName, assembly = type.Assembly.GetName().Name, base_type = type.BaseType?.FullName,
            is_enum = type.IsEnum, total_methods = methods.Length,
            methods = methods.Take(250).Select(m => new { name = m.Name, is_static = m.IsStatic,
                return_type = m.ReturnType.ToString(), parameters = m.GetParameters().Select(p => new { name = p.Name, type = p.ParameterType.ToString() }).ToArray() }).ToArray(),
            fields = type.GetFields(own).Where(f => !f.Name.StartsWith("Native", StringComparison.Ordinal)).Take(100)
                .Select(f => new { name = f.Name, type = f.FieldType.ToString(), is_static = f.IsStatic,
                    constant = type.IsEnum && f.IsLiteral ? f.GetRawConstantValue() : null }).ToArray(),
            properties = type.GetProperties(own).Take(100).Select(p => new { name = p.Name, type = p.PropertyType.ToString() }).ToArray() };
    }
}
