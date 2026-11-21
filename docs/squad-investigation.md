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

FMTeamBindings 0.1.1 records type shapes and allowlisted static property descriptors. No native data channels or unknown getters are invoked. Exact Steam/build hash guard matches FMFaceRefresh 0.2.3. Existing refresh DLL is unchanged. A separate plugin is needed because static PE metadata does not contain the native descriptor implementation/string values.

User action: close game, update, run install_team_bindings.bat, start game and wait ~60s on main menu, export_team_bindings.bat, attach team-bindings.json. A save load or image operation is unnecessary. If signatures/ID storage differ, report contains shapes and errors; do not guess offsets.

After descriptors identify an actual native current-team/team-kind path, inspect exact signatures and prepare a bounded read-only runtime query or a verified save reader. Validate team IDs and native type values against the user's three controlled assignments and additional club structures before enabling a global filter. This remains incomplete until verified in game.

## Event filtering requirements

Preserve registered_team_id and prior/destination squad evidence in baseline/event rows. Incoming selection uses destination tier; outgoing uses previous tier, matching the same selected club direction. A Manchester United first-team departure filter must not accept an U18 departure merely because Arsenal receives that player into its first team. Unknown stays explicit, never silently treated as first/youth. Existing club transfers, loan-type filters and manual requests must retain their semantics; internal same-club promotions currently do not create a transfer job.

## Runtime schema attempt received 2026-11-21

The first 0.1.0 report contains complete type shapes but no schema rows: four types
stopped at `binding_kind_not_enum`, PersonReference exceeded 1024, and the database
record base had no schema descriptors. This is a diagnostic implementation bug, not
evidence that the game cannot distinguish squads.

Actual BindingKind derives from Il2CppSystem.ValueType, with Kind (enum Invalid=0,
Value=1, Reference=2), Reference (ReferenceID), Type (Il2CppSystem.Type), and IsList.
PropertyID and ReferenceID are CLR structs with public `id: UInt32` and get_ID.
ReferenceID.GetInfo returns ReferenceIDInfo inheriting IdentifierInfo.get_Name.
IdentifierUtils.GetName<TIdentifier>(TIdentifier) returns String. These are descriptor
registry lookups, not player queries. DatabaseRecordReference has only record identity
and serialization members and is now retained as a supporting shape only.

Fix in app 0.16.4 / DLL 0.1.1: exact wrapper getters, independent property names and
descriptions/kinds, per-property errors, preserved declared/actual counts, chunked scan
(32 rows or ~5ms per tick), limit 8192 with count recorded on overflow. Fake bindings
now mirror the real wrapper shape rather than incorrectly using a BindingKind enum.
User must reinstall only FMTeamBindings with game closed, rerun game and export.
No team-kind values have been obtained yet; the global filter remains incomplete.

## Successful schema report received 2026-11-21

FMTeamBindings 0.1.1 completed without errors: Team 478, TeamSquad 4, Person 1302,
Club 518, SquadOverviewPlayer 13 properties. All descriptions are empty but names,
kinds and reference targets are valid. Important verified properties:

| Reference | Property | ID | Kind / target |
|---|---|---:|---|
| Team | IsFirstTeam | 1232293204 | Value, dynamic type |
| Team | TeamType | 1416919408 | Value, dynamic type |
| Team | TeamTypeStringDefault | 1651004725 | Value, dynamic type |
| Team | TeamTypeStringTypeOnly | 1295219302 | Value, dynamic type |
| Team | Club | 825630752 | Reference club |
| Person | Team | 1415930221 | Reference team |
| Person | UniqueId | 1970170212 | Int32 |
| Person | Index | 1883858041 | Value, dynamic type |
| Club | ReservesTeam | 1114862952 | Reference team |
| Club | YouthTeam | 1181434674 | Reference team |
| Club | YouthTeam3 | 1634489434 | Reference team |
| Club | YouthTeam4 | 1181955121 | Reference team |
| Club | YouthTeam5 | 1934847574 | Reference team |

Person.TeamType is a DisplayValuePair reference, not the same kind as Team.TeamType.
Do not decode these by the shared property ID alone. TeamSquad contains only position
group lists, not an actual team kind. DB table enum Team=24, Club=3, Person=1 is verified.

Next diagnostic DLL 0.2.0 keeps the schema scan and adds passive UI-value copies from
Bindings.Get(ref Key) and SetInternal(ref Key, TypedValue, SetFlags). Exact path getter
GetPathDebug(ref Key) is verified. No new channels, SendEvent, or active binding reads
are requested. Primitive TypedValue.Get<T> uses only an exactly matching reported CLR
type; string uses AsString. Known Team/Club references expose verified Index/Type getters;
InteropReference exposes verified GetPersistentIdentity. Other values stay opaque.

Counts/timestamps/paths are observations, not yet proof of squad mappings or completeness.
User must reinstall team diagnostic only, load save, visit first/U21/U18 squad screens
and both player profiles within 10 minutes, then export. No save edits required.
Global feature still requires record ID/type validation; no slot-based shortcut added.
