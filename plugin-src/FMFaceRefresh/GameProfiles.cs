namespace FMFaceRefresh;

/// <summary>Only exact binary sets collected from the reported Steam builds.</summary>
public static class GameProfiles
{
    private static readonly string[] Files = { "fm.exe", "GameAssembly.dll", "fm_Data/Plugins/x86_64/game_plugin.dll" };
    private static readonly Dictionary<string, string[]> Hashes = new(StringComparer.Ordinal) {
        ["26620374"] = new[] {
            "a8247abcb57f409b4b45daf28234f09aca335a34e93b753004f1d438efb02349",
            "3f4a26c4869d6429d2e73c276adc64bdfaf6f3c86ce44fe0de93d14683a5d7e9",
            "d12202dd01c3911d4c4e55e778f37b2251ffb10f9cf8cecc3b9ec08ece622c6b" },
        ["26797085"] = new[] {
            "f8a46c63cdaab5710a6520094c93e0766998a9dbb07161be7923b6ac13e09fe6",
            "8b5707a924a6c8cb493cd67bc620be25a456ae5dc6b6f313f3f1d4f70fdeb552",
            "4781439443abfb4b8197de03f1bed5b76063c862d014cfe01c5f54d83c9875ee" }
    };

    public static string Resolve(string? build, Func<string, string> hash)
    {
        if (build is null || !Hashes.TryGetValue(build, out var expected))
            throw new InvalidOperationException("unsupported_platform_or_steam_build");
        for (var i = 0; i < Files.Length; i++)
            if (hash(Files[i]) != expected[i])
                throw new InvalidOperationException("game_file_hash_mismatch:" + Files[i]);
        return "fm27-steam-" + build + "-v1";
    }
}
