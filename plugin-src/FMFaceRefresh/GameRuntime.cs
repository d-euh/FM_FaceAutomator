using System.Collections;
using System.Reflection;
using Il2CppInterop.Runtime.InteropTypes;

namespace FMFaceRefresh;

/// <summary>Resolve generated wrappers by exact signatures; never use hardcoded memory offsets.</summary>
public sealed class GameRuntime : IGraphicsRuntime
{
    private const BindingFlags All = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static;
    private readonly Type resource, panel, manager;
    private readonly MethodInfo find, il2cppType, rescan, clear, reload, convert;
    private readonly List<object> delegateRoots = new();
    public Dictionary<string, object?> Observations { get; } = new();

    public static Type GameType(string assembly, string name) => Assembly.Load(assembly).GetType(name, true)!;
    public static MethodInfo Method(Type type, string name, params string[] parameters)
    {
        var methods = type.GetMethods(All).Where(m => !m.IsGenericMethodDefinition && m.Name == name
            && m.GetParameters().Select(p => p.ParameterType.FullName).SequenceEqual(parameters)).ToArray();
        return methods.Length == 1 ? methods[0] : throw new MissingMethodException(type.FullName, name + "(" + string.Join(",", parameters) + ")");
    }
    private static object? Call(object instance, string getter) => Method(instance.GetType(), getter).Invoke(instance, null);
    private static bool Bool(object instance, string getter) => Call(instance, getter) is true;

    public GameRuntime()
    {
        resource = GameType("SI.Core", "SI.Core.ResourcesSubsystem");
        panel = GameType("SI.Bindable", "SI.Bindable.PanelManager");
        manager = GameType("FM.UI", "FM.UI.ContinueManagerModule");
        find = Method(GameType("UnityEngine.CoreModule", "UnityEngine.Resources"), "FindObjectsOfTypeAll", "Il2CppSystem.Type");
        il2cppType = Method(GameType("Il2CppInterop.Runtime", "Il2CppInterop.Runtime.Il2CppType"), "From", "System.Type");
        rescan = Method(resource, "RescanLocalPaths", "Il2CppSystem.Action");
        clear = Method(resource, "ClearCache"); reload = Method(panel, "ReloadPanels");
        if (rescan.IsStatic || rescan.ReturnType != typeof(void) || clear.IsStatic || reload.IsStatic)
            throw new InvalidOperationException("Unexpected graphics API signature");
        convert = GameType("Il2CppInterop.Runtime", "Il2CppInterop.Runtime.DelegateSupport").GetMethods(All)
            .Single(m => m.Name == "ConvertDelegate" && m.IsGenericMethodDefinition && m.GetParameters().Length == 1);
    }

    private IEnumerable<object> Objects(Type type)
    {
        var nativeType = il2cppType.Invoke(null, new object[] { type });
        var array = find.Invoke(null, new[] { nativeType }) as IEnumerable ?? throw new InvalidOperationException("Object array unavailable");
        foreach (var item in array)
        {
            if (item is not Il2CppObjectBase native) throw new InvalidOperationException("Object wrapper unavailable");
            yield return Activator.CreateInstance(type, new object[] { native.Pointer })!;
        }
    }

    private object Unique(Type type)
    {
        var instances = Objects(type).Take(2).ToArray();
        return instances.Length == 1 ? instances[0] : throw new InvalidOperationException("Expected one " + type.FullName);
    }

    public FrameState State()
    {
        Observations.Clear();
        var managers = Objects(manager).Where(c => Bool(c, "get_m_active") && Bool(c, "get_m_isInMainGameScene")).Take(2).ToArray();
        if (managers.Length != 1) return new(false, "save_not_ready_or_multiple_managers");
        var c = managers[0];
        if (Bool(c, "get_IsLoading") || Bool(c, "get_IsInProcessingCardState") || Bool(c, "get_m_isProcessingInstantResult"))
            return new(false, "game_loading_or_processing");
        var flags = Call(c, "get_m_gameStateFlags") ?? throw new InvalidOperationException("Game flags unavailable");
        Observations["flags_type"] = flags.GetType().FullName;
        var stateHolder = Call(c, "get_m_continueState") ?? throw new InvalidOperationException("Game state unavailable");
        Observations["state_holder_type"] = stateHolder.GetType().FullName;
        var state = Call(stateHolder, "get_Value") ?? throw new InvalidOperationException("Game state value unavailable");
        Observations["flags"] = flags.ToString(); Observations["state"] = state.ToString();
        Observations["flag_values"] = Enum.GetNames(flags.GetType()).Select(n => new { name = n, value = ((Enum)Enum.Parse(flags.GetType(), n)).ToString("D") }).ToArray();
        Observations["state_values"] = Enum.GetNames(state.GetType()).ToArray();
        var policy = GameStatePolicy.Check(flags.ToString()!, state.ToString()!, Enum.GetNames(flags.GetType()), Enum.GetNames(state.GetType()));
        if (!policy.Idle) return policy;
        var resources = Unique(resource);
        if (Method(resource, "get_IsInitialised").Invoke(null, null) is not true || !Bool(resources, "get_AddressablesInitialised"))
            return new(false, "graphics_not_initialised");
        var scans = Call(resources, "get_m_pendingScans") ?? throw new InvalidOperationException("Pending scan list unavailable");
        Observations["pending_scans"] = Call(scans, "get_Count");
        if (Convert.ToInt32(Observations["pending_scans"]) != 0) return new(false, "graphics_scan_in_progress");
        return new(true, "idle");
    }

    public bool ContainsRegisteredPath(string pack)
    {
        var registrations = Call(Unique(resource), "get_m_localPaths")
            ?? throw new InvalidOperationException("Registered graphics roots unavailable");
        var count = Convert.ToInt32(Call(registrations, "get_Count"));
        Observations["registered_path_count"] = count;
        if (count < 0 || count > 10000) throw new InvalidOperationException("Invalid root count");
        var item = Method(registrations.GetType(), "get_Item", "System.Int32");
        for (var index = 0; index < count; index++)
        {
            var registration = item.Invoke(registrations, new object[] { index });
            if (registration is null) continue;
            Observations["registration_string_getters"] = registration.GetType().GetMethods(All)
                .Where(m => !m.IsStatic && m.Name.StartsWith("get_") && m.ReturnType == typeof(string) && m.GetParameters().Length == 0)
                .Select(m => m.Name).ToArray();
            foreach (var getter in registration.GetType().GetMethods(All).Where(m => !m.IsStatic && m.Name.StartsWith("get_")
                     && m.ReturnType == typeof(string) && m.GetParameters().Length == 0
                     && new[] { "path", "folder", "root" }.Any(k => m.Name.Contains(k, StringComparison.OrdinalIgnoreCase))))
            {
                if (getter.Invoke(registration, null) is not string root || !Path.IsPathRooted(root)) continue;
                var relative = Path.GetRelativePath(Path.GetFullPath(root), Path.GetFullPath(pack));
                if (relative != ".." && !relative.StartsWith(".." + Path.DirectorySeparatorChar) && !Path.IsPathRooted(relative)) return true;
            }
        }
        return false;
    }

    public void Rescan(Action completed)
    {
        var native = convert.MakeGenericMethod(rescan.GetParameters()[0].ParameterType).Invoke(null, new object[] { completed })
            ?? throw new InvalidOperationException("Completion delegate unavailable");
        delegateRoots.Add(native); // Retain through completion, including uncertain timeouts.
        rescan.Invoke(Unique(resource), new[] { native });
    }

    public void ClearAndReload()
    { clear.Invoke(Unique(resource), null); reload.Invoke(Unique(panel), null); }
}
