# Squad classification investigation

## Barcelona assignments supplied and checked 2026-11-23

The user identified `2000467065` (오리안 고렌) as Barcelona B
and `2000557918` (오스카 메디나) as Barcelona U19 in the supplied
career. These are user-confirmed in-game assignments; the following registration
and relationship fields were independently read from all three supplied saves.

| User-confirmed assignment | Player ID | Registered team | Effective club | Team's storing club | Candidate type |
|---|---:|---:|---:|---:|---:|
| Barcelona B | 2000467065 | 1340 | 1708 | 1668 | 0 |
| Barcelona U19 | 2000557918 | 29351 | 1708 | 1708 | 11 |

Both registrations and candidate type values are identical across the three saves.
The B player's `team_club_uid` is 1668, and that club's `parent_club_uid` is 1708.
The parent's team list explicitly includes team 1340 with storing club 1668 and
`is_affiliate=True`. The U19 team belongs directly to club 1708. Both players'
contracts name the parent's main team 1364, so that contract reference cannot
identify their actual squad assignment.

This supplies the requested independent assignment evidence for the second club.
It also confirms the slot counterexample: Barcelona's U19 occupies slot 1 and
B team slot 2, whereas the controlled Manchester United reserve and youth teams
occupy slots 1 and 2 respectively. Those positions are not general role rules.

The candidate type 0 cannot distinguish a B team's own main team from the parent
club's main team. The observed parent/child relationship must not be lost. Type
11 now has a user-confirmed U19 example, but the candidate field is still not a
validated saved `IsFirstTeam` or `Club.YouthTeam`/`ReservesTeam` reference. A
controlled affiliate link alone does not establish which of the game's explicit
reserve/youth properties selects it for every club structure.

Verification: the existing read-only diagnostic completed in strict mode for
both players in all three saves. Local assertions checked both registrations,
the child's parent link, the parent's controlled-team entry, unchanged comparison
fields, and the two candidate type values. These checks validate the observations,
not a new classifier. Raw results remain under `/tmp`; only this evidence summary
is committed. No production behavior, native API, or build support was changed.

## Actual controlled-save comparison 2026-11-23

The user supplied the three controlled saves through the `analysis-v2` release.
All three were downloaded successfully and read sequentially with the pinned
`fmsave 0.12.6` reader in strict mode. They are FM27 `27.1.0+2505117`, dated
2028-07-07. This is the existing compatible-save build, not a newly supported
native integration profile. The reader still warns that this build borrows some
FM27 layouts; successful structural checks are not semantic verification.

Both controlled players reproduce the earlier registration transition:
first team 540, reserve 28346, youth 28347. The parsed club records for the
five inspected clubs are byte-identical across the three saves. Moving these
players changes registration, not those clubs' stored team lists/relationships.

Additional byte inspection found candidate team-record fields, beyond the public
reader's `Team` model. After checking the candidate header's team identity against
the club team list and its owner reference against the club index, 44,337 of
47,155 listed own teams have one matching candidate in each save. No duplicate
candidate survives those checks. The candidate identity, owner, record kind,
type value, and flag are unchanged across all three snapshots for those matches.
This is research coverage, not proof of a complete or authoritative record reader;
2,818 listed own teams remain unmatched by this candidate scan.

For the three controlled Manchester United teams, the candidate type values are
0, 10, and 12. These agree with the prior successful native `TeamType` probe in
this document. The club's fourth listed team has candidate value 22; its actual
squad role remains unverified. Fourteen candidate type values occur in the
matched records, so the three controlled teams do not establish a global mapping.

A concrete counterexample to using type values alone: the separately stored
Barcelona B and Bayern II teams have candidate type 0, as do their parent clubs'
main teams. The save reader links those teams into the parent club's controlled
team list. This is a storage observation, not an in-game confirmation of how the
parent club's `ReservesTeam` property resolves. Treating every candidate type 0
as the selected parent club's first team would discard that distinction.

Outcome: there is promising saved team-type evidence, but the saved equivalents
of `IsFirstTeam` and the club's explicit reserve/youth relationships have not been
identified and validated. No production classifier, dependency, native API or
build support was changed. Existing restricted-scope safeguards remain in place.

Next verification needs the actual first/reserve/youth relationships for a club
with a separately stored B team and a different youth structure in this same
career. An existing native team-bindings report with these references, or known
in-game assignments with player IDs, supplies independent ground truth for
further record inspection. Names, slot positions, or the candidate numbers alone
are not that ground truth. The three saves cover assignment changes within one
club, not a change to the reserve/youth relationships themselves.

All original saves, decompressed sections, byte-inspection scripts, and extracted
records remain outside Git under `/tmp`. No save was rewritten and no AI image
generation or native game query was invoked. The source-inspection section below
describes the earlier state before these saves became available.

## Save-only investigation resumed 2026-11-23

Goal: resolve squad roles from the connected save without waiting for the running
game. This section records source inspection, not a new in-game verification.

The installed reader is `fmsave 0.12.6`. Upstream `rhiever/fmsave` main at
`755fe9c` (release 0.14.3) was also inspected. Both versions expose the same
`Team` fields: `team_id`, `slot`, `club_uid`, and `is_affiliate`.
`models/clubs.py` explicitly says which reserve/youth side each own slot holds
is unknown. Neither model exposes `IsFirstTeam` or the club's explicit reserve
and youth relationships. `readers/clubs.py` builds slots by enumerating stored
team IDs; that enumeration does not decode a role. Upstream's
`experimental_span()` decodes fixture cores/rules, not those team relationships.
An upgrade alone therefore does not supply the missing classification.

Our `engine.read_source()` already retains each player's `team_id` as
`registered_team_id`. Existing controlled-save results below verify registration
changes for one club; they do not establish a general slot-to-role mapping.
The existing `squad_diagnostics.py` report exports those same decoded fields,
so repeating that JSON export alone will not reveal the missing raw relationship.
The attached `team-metadata.json` contains runtime metadata, not a saved game.
No actual `.fm` file is available in the current repository or attachment folders.

Next evidence and acceptance criteria:

1. Obtain an actual supported FM27 save plus the in-game first/reserve/youth
   assignments of named players (include player IDs). The earlier three controlled
   saves, if still available, are useful; one save with known assignments is enough
   to begin inspecting records. Keep all real saves and extracted bytes out of Git.
2. Locate the stored team records/club relationships and resolve their identities
   against player registration and the observed assignments. Changes in a player's
   registration identify the team, but do not by themselves identify a role field.
3. Verify any candidate role/reference layout against a second club with a different
   structure, including a separately stored B/reserve club where available. Do not
   turn a correlation in slots, age, names, contracts, or numeric codes into a rule.
4. Only then integrate the verified reader, retain direction-specific source and
   destination evidence, and add synthetic regressions for malformed/missing refs
   and free-agent gaps. Unknown roles must still prevent restricted-scope AI calls.

No production parser, dependency, supported-build gate, native API, or classification
behavior was changed during this source-inspection step. Whether the needed role
relationships can be decoded from the available save remains unverified.

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

## Successful runtime values received 2026-11-21

DLL 0.2.0 report: 204 distinct path/value observations, 31,399 binding events,
8,591 inspected, no read errors/dropped rows. Real displayed values:

| Team native record index | UI label | Prior controlled save team ID |
|---:|---|---:|
| 540 | 성인 선수단 (senior squad) | 540 |
| 28346 | U21 팀 | 28346 |
| 28347 | 유소년 팀 (U18) | 28347 |

Main/first flags are true for the senior view and false for U21/U18 views.
Human.Team.TeamContainer.HighestLevelYouthTeam refers to 28346; SecondHighestLevelYouthTeam
refers to 28347. U21 being a reserve side in the user's controlled setup must not be
promoted into a universal slot/age/category convention; the native container calls it
a youth level. A player Person.Team reference to 28347 was also observed. These match
the controlled assignments, but the two test-player unique IDs were not decoded yet.

UniqueId and some other numeric values use SI.Core.DynamicNumber (75 opaque rows).
Do not reinterpret its memory as Int32. In particular, native Club record index 409 is
used for the Manchester United context while the save's club UID/unique ID is 680.
Native indexes and actual unique IDs are not interchangeable. Runtime scalar TeamType
was not observed; localized strings and flags are not a complete numeric enum mapping.
System.String values can contain FM control/link encoding; do not equate the full raw
string with a clean display name or scan arbitrary base64 contents for IDs.

Next prepared step (app 0.16.6): static helper 0.2.0 includes DynamicNumber and its nested
types, conversion/constructor signatures, generic constraints, IDataHandler/Bindings
handler API, InteropReference factory/Pair, ChannelData/Action/Mode, DB-reference
constructors. All are PE metadata only. The metadata scanner now handles interface nil
base handles and tests ensure no constructors/conversions/getters are executed.

User action: update, run export_team_metadata.bat, attach team-metadata.json. Game may
remain running; no plugin reinstall/restart, player movement or repeat UI visits needed.
The next implementation must validate numeric conversions and safe targeted read lifecycle
against these types before claiming general automatic squad filtering. Existing diagnostic
DLL 0.2.0 and refresh DLL 0.2.3 remain byte-for-byte unchanged in this release.

## Numeric / query signatures received 2026-11-21

Static 0.2.0 report has no assembly errors. DynamicNumber is a CLR value type, with
NumberKind byte enum SignedWhole=0/UnsignedWhole=1/FloatingPoint=2/Invalid=3. Verified
GetLong/GetULong take FloatToWholeConversion; GetDouble takes no argument. Truncate=0,
Floor=1, Round=2, Ceil=3. Read whole numbers with matching signedness, never via double.
TypedValue.Get<T>() has no generic constraints. TeamReference(int index), TypedValue.Create<T>,
Bindings.Create/Set/Remove, CreateGroup, GroupBuilder.Add/Build, Group.IsDone/Get/Dispose
signatures are now known. Channel structs/actions were also captured, but raw native
channel IDs/keys are not allocated or guessed by the implementation.

App 0.16.7 / diagnostic DLL 0.3.0 adds a bounded probe through a private temporary
binding root on an existing observed game Binding owner. It requires human native team
540 and two seconds of the same safe-game policy used by the working refresh bridge.
Main team properties include the two native youth refs; only returned refs matching
28346/28347 enter the next two bounded queries. This is a controlled diagnostic, not a
production table assigning these IDs or slots global meanings.

Reflection signatures are validated before creating nodes, including a span constructor
accepting rooted Il2CppStructArray<char>. No unrooted native string spans/offsets are
constructed. Full span shapes/constructors and initialisation stage are recorded if
interop support differs. Group and private root cleanup run even after timeout/busy or
partial Begin failure; uncertainty is reported and stops new queries. Native SDK
lifecycle is mocked in tests; actual game behavior remains unverified.

User action: close game, update and reinstall team diagnostic with install_team_bindings.bat,
start game, load Manchester United save, do not advance and wait 1–2 minutes, then
export_team_bindings.bat and attach team-bindings.json. No repeated squad/player UI
navigation is required for this probe. Refresh DLL remains 0.2.3 unchanged.

## Successful targeted probe received 2026-11-21

DLL 0.3.0 state complete, all three groups/root nodes created and disposed/removed,
no per-field/query/cleanup errors. Native maximum group size = 16.

| Native index | UniqueId | IsFirstTeam | TeamType | Club.UniqueId | Exact role |
|---:|---:|---|---:|---:|---|
| 540 | 680 | true | 0 | 680 | first |
| 28346 | 2000778736 | false | 10 | 680 | Club.ReservesTeam |
| 28347 | 2000778737 | false | 12 | 680 | Club.YouthTeam |

All three Club native indexes are 409. Native index, team UID and club UID must remain
separate. TeamContainer highest youth also points to U21; prioritize the explicit
reserve relationship over generic youth container membership. These numbers are
observed examples, not a global mapping of type codes or slots.

Implementation app 0.17.0 / DLL 0.4.0: generalized 1–4 team request batches through
owned binding groups, local session/epoch/snapshot-scoped file IPC, heartbeat/expiry,
source club and human-club proof, cache per source snapshot and native epoch.
No hardcoded control IDs in service calls. The old optional controlled probe constructor
exists only for its tests/diagnostic compatibility. Production always supplies targets.

Save events now retain from_team_id/from_registered_club_id including free-agent gaps.
Scope has first/reserve/youth inclusion, default all. Candidate unknown events remain
queued and are resolved before Codex; unknown blocks with automatic preflight retry.
Both selected sides are a union, while each side uses its own registered team. Direct
manual generation bypasses auto-scope. Already-paid results recheck role before apply.
Incoming assignment is refreshed from current people; source assignment stays frozen.
Contract-only registration mismatch does not assume first-team status.

Classifier uses native bool and explicit reserve/youth refs; integer type/age/name/slot
are evidence only. Missing/unmatched/B-team relationships stay unknown. All categories
selected require no native lookup. Verified native API path is reused; world-wide team
structures are not claimed tested. Local IPC, arbitrary bounded target lists, cancellation,
cleanup, direction union, paid-result holding, proof mismatch and no-AI-on-unknown are
covered in unit/fake-runtime tests. Running game must contain the same connected save.

User next step is installation of DLL 0.4.0 and ordinary transfer/filter testing in app,
not another mandatory diagnostic round. Refresh DLL remains unchanged at 0.2.3.
