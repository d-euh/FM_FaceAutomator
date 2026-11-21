using System.Reflection;
using Il2CppInterop.Runtime.InteropTypes.Arrays;

namespace FMTeamBindings;

// A private temporary binding subtree uses the same read-only properties as the UI.
// Nothing is assigned to an existing game/UI path. Dispose + Remove always target our root.
public sealed class TeamQueryRuntime : ITeamProbeRuntime
{
    public static string InitialisationStage { get; private set; } = "not_started";
    public static readonly string[] Properties = { "UniqueId", "Name", "IsFirstTeam", "TeamType", "TeamTypeStringDefault",
        "Club", "Club.UniqueId", "Club.Name", "Club.ReservesTeam", "Club.YouthTeam", "TeamContainer.HighestLevelYouthTeam", "TeamContainer.SecondHighestLevelYouthTeam" };
    private readonly BindingObserver observer;
    private readonly ConstructorInfo teamConstructor, spanConstructor;
    private readonly MethodInfo create, set, remove, pathDebug, validKey, createGroup, add, build, isDone, read, dispose, count, makeValue;
    private readonly object temporary, setDefault, groupDefault;
    private readonly List<object> roots = new();
    private object? owner, key, group;
    private readonly string prefix = "FMFaceProbe" + Guid.NewGuid().ToString("N");
    private bool createAttempted, builderAllocated;
    public bool Ready => observer.BindingOwner is not null && observer.HumanTeamIndex == 540;
    public int groups_created { get; private set; }
    public int groups_disposed { get; private set; }
    public int temporary_roots_created { get; private set; }
    public int temporary_roots_removed { get; private set; }
    public TeamQueryRuntime(Func<string, Type> resolve, BindingObserver observer)
    {
        InitialisationStage = "reference_and_value_signatures";
        this.observer = observer;
        var bindings = resolve("SI.Bindable.Bindings");
        var keyType = resolve("SI.Bindable.Bindings+Key");
        var value = resolve("SI.Core.TypedValue");
        var team = resolve("FM.UI.TeamReference");
        var nodeFlags = resolve("SI.Bindable.Bindings+NodeFlags");
        var setFlags = resolve("SI.Bindable.Bindings+SetFlags");
        var groupFlags = resolve("SI.Bindable.Bindings+GroupFlags");
        temporary = Enum.Parse(nodeFlags, "Default"); setDefault = Enum.Parse(setFlags, "Default"); groupDefault = Enum.Parse(groupFlags, "None");
        teamConstructor = team.GetConstructor(new[] { typeof(int) }) ?? throw new MissingMethodException("TeamReference(index)");
        makeValue = value.GetMethods(BindingFlags.Public | BindingFlags.Static).Single(m => m.Name == "Create"
            && m.IsGenericMethodDefinition && m.GetGenericArguments().Length == 1 && m.GetParameters().Length == 1
            && m.GetParameters()[0].ParameterType.IsGenericParameter && m.ReturnType == value).MakeGenericMethod(team);
        var candidates = bindings.GetMethods().Where(m => m.Name == "Create" && !m.IsStatic && m.ReturnType == keyType
            && m.GetParameters().Length == 2 && m.GetParameters()[1].ParameterType == nodeFlags).ToArray();
        create = candidates.Single();
        var span = create.GetParameters()[0].ParameterType.GetElementType()!;
        if (span is null || !span.IsGenericType || span.GetGenericTypeDefinition().FullName != "Il2CppSystem.ReadOnlySpan`1"
            || span.GetGenericArguments()[0] != typeof(char)) throw new InvalidOperationException("unexpected_span_type");
        // A rooted native char array avoids passing a span backed by an unrooted
        // temporary string across reflection calls. No pointer construction/offsets.
        InitialisationStage = "rooted_char_span_constructor";
        spanConstructor = span.GetConstructors().Single(c => c.GetParameters().Length == 1
            && c.GetParameters()[0].ParameterType.IsGenericType
            && c.GetParameters()[0].ParameterType.GetGenericArguments().SequenceEqual(new[] { typeof(char) })
            && (c.GetParameters()[0].ParameterType.GetGenericTypeDefinition().FullName is
                "Il2CppInterop.Runtime.InteropTypes.Arrays.Il2CppStructArray`1" or "Il2CppInterop.Runtime.InteropTypes.Arrays.Il2CppArrayBase`1")
            && c.GetParameters()[0].ParameterType.IsAssignableFrom(typeof(Il2CppStructArray<char>)));
        InitialisationStage = "group_and_cleanup_signatures";
        set = BindingObserver.Method(bindings, "Set", "System.Void", keyType.FullName! + "&", value.FullName!, setFlags.FullName!);
        pathDebug = BindingObserver.Method(bindings, "GetPathDebug", "System.String", keyType.FullName! + "&");
        validKey = BindingObserver.Method(keyType, "IsValid", "System.Boolean");
        remove = BindingObserver.Method(bindings, "Remove", "System.Void", keyType.FullName! + "&");
        createGroup = BindingObserver.Method(bindings, "CreateGroup", "SI.Bindable.Bindings+GroupBuilder", keyType.FullName!, groupFlags.FullName!);
        var builder = createGroup.ReturnType;
        add = BindingObserver.Method(builder, "Add", builder.FullName!, "System.Int32", keyType.FullName! + "&", span.MakeByRefType().FullName!);
        build = BindingObserver.Method(builder, "Build", "SI.Bindable.Bindings+Group", "SI.Bindable.Bindings+GroupChangedCallback");
        var result = build.ReturnType;
        isDone = BindingObserver.Method(result, "get_IsDone", "System.Boolean");
        count = BindingObserver.Method(result, "get_Count", "System.Int32");
        read = BindingObserver.Method(result, "Get", value.FullName!, "System.Int32");
        dispose = BindingObserver.Method(result, "Dispose", "System.Void");
        InitialisationStage = "ready";
    }
    private object Span(string text)
    {
        var array = new Il2CppStructArray<char>(text.ToCharArray());
        roots.Add(array);
        var span = spanConstructor.Invoke(new object[] { array }); roots.Add(span);
        return span;
    }
    public void Begin(int teamIndex)
    {
        if (!Ready || owner is not null) throw new InvalidOperationException("query_owner_not_ready");
        owner = observer.BindingOwner;
        var reference = teamConstructor.Invoke(new object[] { teamIndex }); roots.Add(reference);
        var actual = (int)BindingObserver.Method(reference.GetType(), "get_Index", "System.Int32").Invoke(reference, null)!;
        var table = BindingObserver.Method(reference.GetType(), "get_Type", "FM.UI.DatabaseTableType").Invoke(reference, null)!;
        if (actual != teamIndex || !table.GetType().IsEnum || Enum.GetName(table.GetType(), table) != "Team")
            throw new InvalidOperationException("team_reference_mismatch");
        var supplied = makeValue.Invoke(null, new[] { reference })!; roots.Add(supplied);
        var rootPath = Span(prefix);
        createAttempted = true;
        key = create.Invoke(owner, new[] { rootPath, temporary })!;
        if (validKey.Invoke(key, null) is not true || (string?)pathDebug.Invoke(owner, new[] { key }) != prefix)
        { key = null; throw new InvalidOperationException("unverified_private_root_handle"); }
        temporary_roots_created++;
        set.Invoke(owner, new[] { key, supplied, setDefault });
        var builder = createGroup.Invoke(owner, new[] { key, groupDefault })!;
        builderAllocated = true; groups_created++; roots.Add(builder);
        for (int i = 0; i < Properties.Length; i++)
            builder = add.Invoke(builder, new[] { (object)i, key, Span(Properties[i]) })!;
        group = build.Invoke(builder, new object?[] { null });
        if (group is null || (int)count.Invoke(group, null)! != Properties.Length)
            throw new InvalidOperationException("query_group_size_mismatch");
    }
    public TeamProbeResult? Poll()
    {
        if (group is null) throw new InvalidOperationException("query_group_missing");
        if (isDone.Invoke(group, null) is not true) return null;
        var result = new TeamProbeResult();
        for (int i = 0; i < Properties.Length; i++)
        {
            try { result.values[Properties[i]] = observer.DecodeSupplied(read.Invoke(group, new object[] { i })!); }
            catch (Exception e) { result.values[Properties[i]] = new() { error = e.GetBaseException().GetType().Name }; }
        }
        return result;
    }
    public void Close()
    {
        Exception? failure = null;
        try
        {
            if (group is not null) { dispose.Invoke(group, null); groups_disposed++; }
            else if (builderAllocated) failure = new InvalidOperationException("unbuilt_group_cleanup_uncertain");
        }
        catch (Exception e) { failure = e; }
        finally
        {
            try
            {
                if (key is not null && owner is not null)
                {
                    if ((string?)pathDebug.Invoke(owner, new[] { key }) != prefix)
                        throw new InvalidOperationException("private_root_identity_changed");
                    remove.Invoke(owner, new[] { key }); temporary_roots_removed++;
                }
                else if (createAttempted) failure ??= new InvalidOperationException("temporary_root_handle_missing");
            }
            catch (Exception e) { failure ??= e; }
            group = null; key = null; owner = null; roots.Clear(); createAttempted = false; builderAllocated = false;
        }
        if (failure is not null) throw new InvalidOperationException("query_cleanup_failed", failure);
    }
}
