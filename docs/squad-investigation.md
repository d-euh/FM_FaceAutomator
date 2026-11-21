# Squad classification investigation

## Confirmed evidence

User-controlled three-save test, FM27 27.1.0+2505117, same club and game date:

| Assigned squad | Player registered team ID | Slot | Club UID / unique ID |
|---|---:|---:|---:|
| Manchester United first team | 540 | 0 | 680 |
| Manchester United U21 | 28346 | 1 | 680 |
| Manchester United U18 | 28347 | 2 | 680 |

Both test players (2000256110 and 2000382120) have exactly this transition. Contract team remains 540; contract status and loan flag do not change. Slot 3 / team 55048 is unverified. This proves registration changes are readable, **not** that slots 0/1/2 mean these tiers for every club/save. Never infer actual squad from age, youth contract, promised playing time or match participation.

## Static metadata received 2026-11-21

33 assemblies, no scan errors, no output compaction. FM.UI candidates truncated at 180 of 298, but its complete type index is present. `TeamReference`, `TeamSquadReference`, `PersonReference`, `ClubReference`, `DatabaseRecordReference`, `SquadOverviewPlayerReference` exist. `TeamReference` derives from `DatabaseRecordReference`.

TeamReference and TeamSquadReference expose only generated reference/schema methods; no current squad getter or team-tier enum was found. Their exact static descriptor signatures include:

- `GetPropertyCountInternal() -> Int32`
- `GetPropertiesInternal(Il2CppSystem.Collections.Generic.List<PropertyID>) -> Void`
- `GetPropertyDescriptionInternal(UInt32) -> String`
- `GetPropertyTypeInternal(UInt32) -> SI.Bindable.Reference.Core.BindingKind`

`ContinueManagerModule.ContextTeamType` is Club/NationalTeam/Neither. It is unrelated to first/reserve/youth. Graphics/match Home/Away enums are also irrelevant. `SI.Data` has portrait/advertising container types, not native football database records. Dynamic binding identifiers/property handlers bridge the native game data.

## Next prepared diagnostic

FMTeamBindings 0.1.0 records type shapes and allowlisted static property descriptors. No native data channels or unknown getters are invoked. Exact Steam/build hash guard matches FMFaceRefresh 0.2.3. Existing refresh DLL is unchanged. A separate plugin is needed because static PE metadata does not contain the native descriptor implementation/string values.

User action: close game, update, run install_team_bindings.bat, start game and wait ~60s on main menu, export_team_bindings.bat, attach team-bindings.json. A save load or image operation is unnecessary. If signatures/ID storage differ, report contains shapes and errors; do not guess offsets.

After descriptors identify an actual native current-team/team-kind path, inspect exact signatures and prepare a bounded read-only runtime query or a verified save reader. Validate team IDs and native type values against the user's three controlled assignments and additional club structures before enabling a global filter. This remains incomplete until verified in game.

## Event filtering requirements

Preserve registered_team_id and prior/destination squad evidence in baseline/event rows. Incoming selection uses destination tier; outgoing uses previous tier, matching the same selected club direction. A Manchester United first-team departure filter must not accept an U18 departure merely because Arsenal receives that player into its first team. Unknown stays explicit, never silently treated as first/youth. Existing club transfers, loan-type filters and manual requests must retain their semantics; internal same-club promotions currently do not create a transfer job.
