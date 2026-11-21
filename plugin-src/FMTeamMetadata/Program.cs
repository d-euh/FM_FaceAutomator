using FMTeamMetadata;

if (args.Length is < 2 or > 3)
{
    Console.Error.WriteLine("Usage: FMTeamMetadata <BepInEx/interop> <output.json> [SteamBuild]");
    return 2;
}
try
{
    var report = MetadataReport.Collect(args[0], args.Length == 3 ? args[2] : null, file => Console.WriteLine("Reading " + file));
    var bytes = MetadataReport.SerializeBounded(report);
    var output = Path.GetFullPath(args[1]);
    Directory.CreateDirectory(Path.GetDirectoryName(output)!);
    var temporary = output + "." + Guid.NewGuid().ToString("N") + ".tmp";
    try { File.WriteAllBytes(temporary, bytes); File.Move(temporary, output, true); }
    finally { if (File.Exists(temporary)) File.Delete(temporary); }
    Console.WriteLine("Metadata-only report written (" + bytes.Length + " bytes)");
    return 0;
}
catch (Exception exception)
{
    Console.Error.WriteLine("Metadata export failed: " + exception.GetType().Name + ": " + exception.Message);
    return 1;
}
