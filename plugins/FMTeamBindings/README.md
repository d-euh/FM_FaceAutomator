# FM Team Binding Reader 0.4.2

Separate BepInEx 6 Unity IL2CPP diagnostic for FM27 Steam build 26620374.
Use `install_team_bindings.bat` with FM27 closed. Start FM27 and load the same save
connected in the app. Choose the squad categories in the transfer detection scope.
The app sends bounded native team-read requests before automatic image generation.
No manual squad/profile navigation or diagnostic export is normally required.

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

The runtime service uses the same owned binding-group API that successfully read and
cleaned all three controlled Manchester United teams in the user's 0.3.0 report.
It accepts 1–4 distinct nonnegative team indexes per request from the app. There are
no hardcoded Manchester United targets in the service. Stable loaded-game state,
exact binary hashes, request/session/epoch/expiry and group capacity are validated.

IPC root: LocalAppData/FMFaceAutomator/team-reader. Status heartbeats expire after
5 seconds. Requests are correlated to a per-save snapshot token; the Python client
validates native club unique IDs and the live human club against save membership.
Changing game state cancels active reads and invalidates cached results. The user must
load the same save in the game as the app has connected.

DynamicNumber keeps signed/unsigned/floating values separate with full integer
precision. Each team group reads at most 15 fields (native reported max is 16).
Read roots have unique names, ownership is checked before Set/Remove, and Dispose
and Remove run on completion, cancellation, busy-state transitions and timeout.
Mailbox write failures do not replay native reads. Cleanup errors disable further
queries until a game restart. Old UI-observation capture remains bounded to ten minutes;
lightweight owner-key updates continue for subsequent save loads.

The Python app classifies first team by IsFirstTeam, reserve by Club.ReservesTeam,
and youth by explicit native youth references (reserve has priority over overlapping
youth refs). Numeric type codes, age and slot order are not guessed. Unmatched teams
remain unknown. Incoming/outgoing are checked on the same side as club scope. No AI
request or facepack apply is authorized by an unknown restricted category.

Existing UI values, gameplay actions and save files are not changed. Private binding
nodes and diagnostic/IPC files are created and removed. No Codex calls occur in this
plugin. The existing FMFaceRefresh DLL is unchanged. See README.md for app usage.

The exact native query path was verified on the user's three teams; the generalized
IPC/client/scope integration is tested with fake game APIs and still needs normal
end-to-end use on the user's PC. Unsupported team relationships remain on hold.

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

Version 0.4.1 retains the first two-second stable-idle check across a batch.
Subsequent teams reuse the continuous idle interval after the previous group is
fully closed. Every tick still checks idle state, and any busy interval resets
the stable timer. Build hashes, signatures, group capacity and cleanup are unchanged.
The scheduler is covered by fake-runtime tests and a DLL build. Actual Windows
FM27 timing and loading of this version require in-game confirmation.

Version 0.4.2 adds context_epoch for reusing completed classifications. Ordinary
processing and recognized busy states preserve it. Loading, human-team changes
and unknown states invalidate it and publish a heartbeat immediately. The query
epoch still cancels active native reads whenever the game becomes busy. The app
reuses evidence only for matching save snapshots, player registration, selection
and fresh session/context heartbeats. Old jobs without such evidence are queried
once. Context transitions are verified with fake-runtime tests and a DLL build.
Actual Windows FM27 behavior of this version requires in-game confirmation.
