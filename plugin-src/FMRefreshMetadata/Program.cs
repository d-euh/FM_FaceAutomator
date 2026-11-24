using System.Text.Json;
using FMFaceRefresh.Diagnostics;

if (args.Length != 2)
{
    Console.Error.WriteLine("Usage: FMRefreshMetadata <FM27 folder> <output.json>");
    return 2;
}
try
{
    var game = Path.GetFullPath(args[0]);
    var output = Path.GetFullPath(args[1]);
    var relative = Path.GetRelativePath(game, output);
    if (relative != ".." && !relative.StartsWith(".." + Path.DirectorySeparatorChar) && !Path.IsPathRooted(relative))
        throw new ArgumentException("Choose an output outside the game folder.");
    var interop = Path.Combine(game, "BepInEx", "interop");
    if (!Directory.Exists(interop)) throw new DirectoryNotFoundException("BepInEx interop is missing.");
    var files = Directory.GetFiles(interop, "*.dll").Concat(new[] {
        Path.Combine(game, "fm.exe"), Path.Combine(game, "GameAssembly.dll"),
        Path.Combine(game, "fm_Data", "Plugins", "x86_64", "game_plugin.dll") }).ToArray();
    if (files.Length == 3 || files.Any(f => !File.Exists(f)))
        throw new FileNotFoundException("Required game/interop files are missing.");
    var before = files.ToDictionary(f => f, f => (new FileInfo(f).Length, File.GetLastWriteTimeUtc(f)));
    var report = Report.Collect(game, Path.Combine(game, "BepInEx"));
    if (files.Any(f => !File.Exists(f) || before[f] != (new FileInfo(f).Length, File.GetLastWriteTimeUtc(f)))
        || !Directory.GetFiles(interop, "*.dll").Order().SequenceEqual(files.Take(files.Length - 3).Order()))
        throw new IOException("Game files changed during export; retry after updating and closing FM27.");
    report["kind"] = "fm_refresh_compatibility";
    report["tool_version"] = "0.1.0";
    report["game_methods_invoked"] = false;
    var bytes = JsonSerializer.SerializeToUtf8Bytes(report);
    if (bytes.Length > 24 * 1024 * 1024) throw new InvalidDataException("Report exceeds 24 MiB.");
    Directory.CreateDirectory(Path.GetDirectoryName(output)!);
    var temporary = output + "." + Guid.NewGuid().ToString("N") + ".tmp";
    try { File.WriteAllBytes(temporary, bytes); File.Move(temporary, output, true); }
    finally { if (File.Exists(temporary)) File.Delete(temporary); }
    Console.WriteLine("Read-only compatibility report saved. No game APIs were executed.");
    return 0;
}
catch (Exception exception)
{
    Console.Error.WriteLine("Export failed: " + exception.GetType().Name + ": " + exception.Message);
    return 1;
}
