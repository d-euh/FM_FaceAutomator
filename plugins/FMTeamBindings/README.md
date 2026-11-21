# FM Team Binding Diagnostics 0.1.0

Separate BepInEx 6 Unity IL2CPP diagnostic for FM27 Steam build 26620374.
Use `install_team_bindings.bat` with FM27 closed. Start the game, wait about 60 seconds
on the main menu, then run `export_team_bindings.bat`. No save load, transfer, AI
request, image deletion, or refresh test is required.

Output: `BepInEx/diagnostics/FMTeamBindings/team-bindings.json`, exported to the app's
`diagnostics/team-bindings.json`. Error reports are useful too. Old reports from before
installation and reports still waiting for the main thread are rejected by the exporter.

The plugin uses the same three-file SHA256/build guard as FMFaceRefresh 0.2.3.
On the main thread it calls only exact allowlisted static binding-schema descriptors
on six FM.UI Reference types. It records property IDs/descriptions/kinds, plus supporting
CLR member signatures without invoking those members. Native property-ID storage must
be unambiguous; no offsets or slot meanings are guessed. Counts/descriptions/output
are bounded. A one-time inert tick postfix remains until process exit.

It does not query players or open binding channels, change game data/context, edit
saves/facepacks, or invoke Codex. The existing refresh plugin is not replaced. There is
no automatic first/reserve/youth filter yet; actual native type values still need verification.

Source: `plugin-src/FMTeamBindings`. Host-only descriptor tests:

```
dotnet run --project plugin-src/FMTeamBindings.Tests -c Release
```

Build using the BepInEx core reference directory:

```
dotnet build plugin-src/FMTeamBindings -c Release -p:BepInExCoreDir=/path/to/BepInEx/core
```

Only the resulting FMTeamBindings.dll and SHA256SUMS are bundled here. Tests use fake
bindings and do not establish success against a running game.
