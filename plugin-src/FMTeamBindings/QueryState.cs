using System.Collections;
using System.Reflection;
using Il2CppInterop.Runtime.InteropTypes;

namespace FMFaceRefresh { public record FrameState(bool Idle, string Reason); }
namespace FMTeamBindings
{
    // Same enum-name policy and confirmed manager getters as the working refresh bridge.
    public sealed class QueryState
    {
        private readonly Type manager;
        private readonly MethodInfo find, nativeType;
        public string Reason { get; private set; } = "initialising";
        private static object? Call(object source, string name)
        {
            var method = source.GetType().GetMethods(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)
                .Single(m => m.Name == name && !m.IsGenericMethodDefinition && m.GetParameters().Length == 0);
            return method.Invoke(source, null);
        }
        public QueryState(Func<string, Type> resolve)
        {
            manager = resolve("FM.UI.ContinueManagerModule");
            find = Assembly.Load("UnityEngine.CoreModule").GetType("UnityEngine.Resources", true)!
                .GetMethods(BindingFlags.Static | BindingFlags.Public).Single(m => m.Name == "FindObjectsOfTypeAll"
                    && !m.IsGenericMethodDefinition && m.GetParameters().Length == 1
                    && m.GetParameters()[0].ParameterType.FullName == "Il2CppSystem.Type");
            nativeType = Assembly.Load("Il2CppInterop.Runtime").GetType("Il2CppInterop.Runtime.Il2CppType", true)!
                .GetMethods(BindingFlags.Static | BindingFlags.Public).Single(m => m.Name == "From"
                    && !m.IsGenericMethodDefinition && m.GetParameters().Length == 1 && m.GetParameters()[0].ParameterType == typeof(Type));
        }
        public bool Idle()
        {
            try
            {
                var array = find.Invoke(null, new[] { nativeType.Invoke(null, new object[] { manager }) }) as IEnumerable
                    ?? throw new InvalidOperationException("manager_array_missing");
                var active = new List<object>();
                foreach (var value in array)
                {
                    if (value is not Il2CppObjectBase wrapped) continue;
                    var item = Activator.CreateInstance(manager, new object[] { wrapped.Pointer })!;
                    if (Call(item, "get_m_active") is true && Call(item, "get_m_isInMainGameScene") is true) active.Add(item);
                    if (active.Count > 1) break;
                }
                if (active.Count != 1) { Reason = "loaded_game_not_ready"; return false; }
                var owner = active[0];
                if (Call(owner, "get_IsLoading") is true || Call(owner, "get_IsInProcessingCardState") is true
                    || Call(owner, "get_m_isProcessingInstantResult") is true) { Reason = "game_loading_or_processing"; return false; }
                var flags = Call(owner, "get_m_gameStateFlags")!;
                var state = Call(Call(owner, "get_m_continueState")!, "get_Value")!;
                if (!flags.GetType().IsEnum || !state.GetType().IsEnum) throw new InvalidOperationException("unexpected_state_type");
                var checkedState = FMFaceRefresh.GameStatePolicy.Check(flags.ToString()!, state.ToString()!,
                    Enum.GetNames(flags.GetType()), Enum.GetNames(state.GetType()));
                Reason = checkedState.Reason; return checkedState.Idle;
            }
            catch (Exception e) { Reason = "state_unavailable:" + e.GetBaseException().GetType().Name; return false; }
        }
    }
}
