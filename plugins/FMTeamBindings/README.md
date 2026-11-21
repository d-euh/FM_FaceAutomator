# FM Team Binding Diagnostics 0.3.0

Separate BepInEx 6 Unity IL2CPP diagnostic for FM27 Steam build 26620374.
Use `install_team_bindings.bat` with FM27 closed. Start the game and load the
Manchester United save. Do not advance the game; wait 1–2 minutes, then run
`export_team_bindings.bat`. No separate squad/profile screen visits, player moves,
AI requests, image deletions or refresh tests are required.

Output: `BepInEx/diagnostics/FMTeamBindings/team-bindings.json`, exported to the app's
`diagnostics/team-bindings.json`. Error reports are useful too. Old reports from before
installation and reports still waiting for the main thread are rejected by the exporter.

The plugin uses the same three-file SHA256/build guard as FMFaceRefresh 0.2.3.
The schema scan runs on the main thread and calls exact allowlisted static binding-schema descriptors
on five FM.UI Reference types (the database-record base has no schema descriptors). It records property IDs/descriptions/kinds, plus supporting
CLR member signatures without invoking those members. BindingKind is the observed
IL2CPP value wrapper containing Kind/Reference/Type/IsList, not an enum. Schema names
come from IdentifierUtils.GetName, reference target names from ReferenceID.GetInfo.
Partial property descriptions and actual counts survive per-item errors. At most 32
properties are read per tick (yield after ~5ms); per-reference count is bounded to 8192.
The export size limit is 8 MiB. Earlier tool-version reports are rejected even if their file
timestamp is recent. Reinstall with install_team_bindings.bat after updating. Native property-ID storage must
be unambiguous; no offsets or slot meanings are guessed. Counts/descriptions/output
are bounded. Diagnostic postfixes remain installed but observation becomes inert after ten minutes.

A bounded passive observer also copies already-supplied TypedValue values from known
football UI paths using exact Get/SetInternal postfix signatures and GetPathDebug.
It never invokes Get/SetInternal itself or opens native data channels. Primitive values
are decoded only for their reported type. Team/club reference indexes and confirmed
InteropReference persistent identities may be copied; other native values stay opaque.
There are 512 unique path/value records maximum, 128 path inspections per tick and a
10-minute capture window. Unknown signatures disable the observer independently of
the schema scan. Values may include player/team names and native record IDs. Reports
with zero observations are exportable and include hook/capture counters.

The targeted probe uses a private temporary binding root, a TeamReference(index),
and the game's normal binding group read API. It starts only for an observed human
team index 540 and stable loaded-game state. Only the main result's native youth
references matching the previously observed 28346/28347 are queried next (max 3 teams).
These indexes are diagnostic examples, never universal squad categories.

DynamicNumber uses its verified Kind/GetLong/GetULong/GetDouble API. No memory offsets,
float-to-ID truncation or lossy double conversion for unsigned integers are used.
Private native char arrays root path spans until cleanup. Missing signatures/span
constructors fail before binding creation; no unverified string-pointer construction.

Every query group has a 15-second deadline and is disposed with its private root
removed on completion/failure/busy state. Partial-build cleanup uncertainty is reported
and stops further queries. Results and root/group counters are exported even on error.
No existing UI values, gameplay/continue events, save files or facepacks are changed,
and no Codex calls are made. The temporary binding tree itself is changed, explicitly
recorded in the report. The existing FMFaceRefresh DLL is not replaced.

Actual native reads and classification still require verification on the user's PC.
There is no production first/reserve/youth filter enabled yet.

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
