using System.Reflection;

namespace FMTeamBindings;

public sealed class DynamicNumbers
{
    private readonly MethodInfo extract, kind, signed, unsigned, floating;
    private readonly object truncate;
    public DynamicNumbers(Type number, MethodInfo genericGet)
    {
        if (number.FullName != "SI.Core.DynamicNumber" || !number.IsValueType)
            throw new InvalidOperationException("unexpected_dynamic_number_type");
        extract = genericGet.MakeGenericMethod(number);
        var kindType = number.GetMethod("get_Kind", Type.EmptyTypes)?.ReturnType
            ?? throw new MissingMethodException("DynamicNumber.Kind");
        if (!kindType.IsEnum || kindType.FullName != "SI.Core.DynamicNumber+NumberKind")
            throw new InvalidOperationException("unexpected_number_kind");
        kind = BindingObserver.Method(number, "get_Kind", kindType.FullName);
        var conversion = number.GetNestedType("FloatToWholeConversion")
            ?? throw new MissingMemberException("FloatToWholeConversion");
        if (!conversion.IsEnum || !Enum.IsDefined(conversion, "Truncate"))
            throw new InvalidOperationException("unexpected_numeric_conversion");
        truncate = Enum.Parse(conversion, "Truncate");
        signed = BindingObserver.Method(number, "GetLong", "System.Int64", conversion.FullName!);
        unsigned = BindingObserver.Method(number, "GetULong", "System.UInt64", conversion.FullName!);
        floating = BindingObserver.Method(number, "GetDouble", "System.Double");
    }
    public void Read(object supplied, ObservedValue result)
    {
        var number = extract.Invoke(supplied, null)!;
        var tag = kind.Invoke(number, null)!;
        result.numeric_kind = Enum.GetName(tag.GetType(), tag);
        switch (result.numeric_kind)
        {
            case "SignedWhole": result.scalar = (long)signed.Invoke(number, new[] { truncate })!; break;
            case "UnsignedWhole": result.scalar = (ulong)unsigned.Invoke(number, new[] { truncate })!; break;
            case "FloatingPoint":
                var value = (double)floating.Invoke(number, null)!;
                if (double.IsFinite(value)) result.scalar = value;
                else result.error = "nonfinite_number";
                break;
            default: result.error = "invalid_dynamic_number"; break;
        }
    }
}
