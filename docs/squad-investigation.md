# Squad classification investigation

## Graphics-refresh 0.2.4 candidate 2026-11-25

The supplied `refresh-compatibility.json` reports Steam 26797085, 179 scanned
assemblies and no read errors. It confirms the three hashes now pinned in
`GameProfiles.cs`. A reduced nonpersonal API fixture records exact refresh/state
method signatures and assembly module IDs. RescanLocalPaths(Action),
RegisterLocalPath(String, Il2CppStringArray), ClearCache(), ReloadPanels(),
ContinueGame(TimerType), both ProcessCurrentContinueFlowState overloads,
ShouldPauseCountdown(), TickSubsystem.Update(), Unity Resources lookup and the
state/registration getters match the existing invocation shapes. Nested metadata
names such as `.TimerType` are not assertions of fully qualified runtime names.

0.2.4 retains the old exact binary set and adds only this observed new set with a
separate request/reply profile. Runtime initialization rechecks binary hashes and
method signatures; all hook signatures are checked before the first Harmony
patch. Unknown builds/mixed or altered files fail closed. Original team DLL
installation/research gates and static baseline Report.ExpectedBuild are not
expanded. Python refresh installation alone accepts the two observed builds;
the runtime applies the binary gates. App transport accepts only the two known
profiles, requires 0.2.4 for the patch profile, and checks matching reply profile.

No new game API or refresh sequence is introduced. Controller/delegate roots,
busy/idle policy, one-shot scan, callback completion, cache/panel reload, timeout
faulting and unload/own-hook cleanup are retained. Linux .NET tests cover actual
hash fixtures, rejection of changed/mixed/unknown sets, old reported game states,
callback/timeout/config-lock and response-delivery behavior. The DLL targets
net6.0 and compiles against the same existing be.697 reference SDK API surface;
the installer still requires the user's be.793+ runtime. The references are not
shipped or substituted into the game. This is not proof of new-game execution.

A fresh DLL/checksum is distributed with the app. Final validation needs the
user to install 0.2.4 with FM27 closed, run the patched game and test refresh on
an existing image without an AI request. Both a fresh live-refresh report
(callback/reload evidence) and actual visual change are needed. Neither Windows
plugin loading nor actual 26797085 refresh completion has been observed here.

## Graphics-refresh Steam 26797085 investigation 2026-11-25

The user's installer screenshot reports Steam build `26797085`; this is not the
save header build `27.1.1+2511875`. No binaries or API observations from that new
game installation are available in this workspace yet. Runtime/installer build
and hash guards remain restricted to 26620374; no DLL was changed or installed.

`export_refresh_compatibility.bat` / `refresh_compatibility.py` and the standalone
`tools/FMRefreshMetadata` helper now collect an offline report from the user's
installation. The helper links the existing PE metadata reader `Report.cs` and
does not load assemblies, execute game APIs or install plugins. It records game
hashes and refresh-related method signatures, including errors, without exposing
installation paths. Input file stamp changes/manifest changes fail the export;
outputs are bounded to 24 MiB, outside the game directory, and published atomically
only after validation. The old report is retained on failure. These are research
tools, not part of the normal app installer or a new runtime support profile.

Windows win-x64 self-contained compilation succeeded. Python wrapper checks and
Linux CLI checks cover the new-build report, PE signature decoding, corrupt DLL
isolation, original-file preservation, no game execution, output boundaries and
old-output preservation. Actual Windows execution and API/cleanup/runtime refresh
on the new game remain unverified. The next required input is the user's generated
`diagnostics/refresh-compatibility.json`; no native support expansion is justified
by the screenshot or save alone.

## FM27 27.1.1 compatibility enabled 2026-11-25

The user authorized a save-reading/classification compatibility update after the
read-only investigation below. Production now explicitly accepts only the two
save-team builds `27.1.0+2505117` and `27.1.1+2511875`. The player reader shares
this explicit compatibility list; strict fmsave and team-table/owner checks remain
in force. Future/unrecognized builds are still rejected. Existing registered
older fmsave builds retain their previous basic-reading behavior, not new squad
classification support.

Role evidence and backend status retain the actual save build. Frozen departure
proofs from either supported build remain valid across a patch upgrade; the
parser rules/version are unchanged. No settings/history/facepack migration or
paid regeneration is introduced. Unknown states/owners remain unknown and
restricted tasks block before AI. Existing Steam build 26620374/native hash/API
gates and DLL binaries are unchanged; this is not support for graphics refresh
on the patched game. Earlier native evidence must not be described as a new
27.1.1 in-game verification.

Unmodified production calls (no in-memory build substitution) subsequently read
both supplied real saves and ingested them in sequence into a disposable workspace.
The old baseline had 95,386 players; the patched snapshot had 95,050. Each had
47,155 club-team entries with actual-build provenance. Manchester United's three
control roles passed for both. The later snapshot added three scoped transfer
jobs; no AI/native request or facepack write occurred. The original files and
user workspace were untouched. UnknownBuildWarnings were retained. Windows/game
execution and patched-game graphics refresh remain unverified.

## FM27 27.1.1 save investigation 2026-11-25

This is a read-only compatibility investigation, not an enabled production build.
The save supplied in `d-euh/any` release `v3` is 171,091,625 bytes, SHA-256
`7dbdf4692c1cedbfceeffdcc4b698952884818d2e909022eeb78d7ccb70e7785`.
Its header reports FM27 `27.1.1+2511875`, game date 2028-09-02.
The released app correctly rejects this build as outside its current allowlist.

A disposable diagnostic process temporarily substituted the candidate build in
memory only. The unchanged `fmsave==0.12.6` strict readers, existing ownership
checks and team decoder read 95,050 players and produced 47,155 club-team entries:
21,445 first, 2,910 reserve, 9,709 youth, and 13,091 unknown. Unknown entries were
not promoted or sent to AI. The raw table contains 55,063 records, including
national teams; this is a different count from production club-team entries.

Comparison with the previously verified 27.1.0 save dated 2028-07-07 found:

- All section schema version numbers match.
- All 55,063 team unique IDs, indexes, secondary IDs, owner indexes, record kinds,
  national markers, raw types and tail flags match.
- All 21,445 club identity/team-reference graphs match.
- 49 raw age fields and one prefix flag changed over the simulated interval.
  The changed prefix is team index 29223, type 1, flags 1 to 128; no new raw
  type/prefix combination appears compared with that older save. This does not
  extend the production set of semantically verified states.
- The decoder's kind/owning-club result for every club-team unique ID matches,
  including the Manchester United first/reserve/youth controls. This is a
  cross-save decoder comparison, not new in-game role verification.

`fmsave` emitted two UnknownBuildWarnings: it has no complete registered layout
for 27.1.1 and borrows existing FM27 layouts, including the 27.1.0 club/finance
layout. Structural success does not establish all field semantics. No new game
UI/native observations were collected. The production allowlist, save decoder
gate and Steam/hash restrictions remain unchanged. The new Steam build number,
game binaries, graphics-refresh DLL compatibility and Windows execution cannot
be established from this save alone. No user settings, queue, facepack or save
was modified and no image/AI request was made.

## Live team lookup removed 2026-11-24

Production classification uses only the verified save decoder. Native fallback,
team-reader connection checks, team DLL installation/export launchers and bundled
team DLL/metadata resources have been removed. Unsupported save builds stay
unknown and restricted tasks block before AI. Existing native authorizations
cannot be reused as save proofs. Legacy native-mode workspaces force a source
refresh even when its stamp is unchanged. Graphics-refresh DLL behavior and its
Steam/hash gates are unchanged. Existing game-folder DLLs are not deleted.

Historical native sources and verification tools remain for reproducibility;
they are not imported or shipped by the app. The sections below describe earlier
investigation stages and are not current installation instructions.

## Application integration 2026-11-23

The verified decoder now lives in `save_teams.py`; the original research import
path remains a compatibility shim. App source reads for save build
`27.1.0+2505117` decode the table once and reconstruct references using the native
observations. Production restricts type/prefix-state combinations to those
observed in the supplied reports and reference-based roles to at most three
participating subteams, the largest observed structure. Unseen shapes remain
unknown; a verified primary team does not depend on unverified sibling refs.
The existing role validator is reused with evidence explicitly marked
`source: save`, not presented as an actual live API response. Owner mismatch
(including a controlled B team relative to its parent) remains unknown as before.

`read_source()` returns shared team evidence and a backend status. `Engine.ingest`
updates its owned `save_squads` SQLite table atomically with the player baseline
and snapshot metadata. Evidence is not copied into every player's row or loaded
as a full JSON map for each job. Upgraded workspaces force one source read even
when the file stamp is unchanged; existing settings, baseline, jobs, paid results
and images are retained. The parser version controls subsequent refreshes.

Restricted-scope preflight reads matching team/club evidence from that snapshot
without a live game context. Arrivals use the latest registered team. Departures
freeze the previous snapshot's known evidence when leaving a club and retain it
in the last-registration record across free-agent gaps. Older jobs without this
new evidence retain their recorded source-team IDs and resolve them from the
saved table. Invalid historical owner/index/version data stays unknown.
Save-based authorization proofs are tied to source snapshot, membership,
direction/settings and reader version, not a running game epoch. File writes
still wait for a stable save; no new pre-save live query is introduced.

Decode failure on the supported build stays in save mode with an explicit error
and no native fallback or AI authorization. Existing supported older-save builds
retain their previous native path. No native API, DLL, Steam profile/hash guard,
or graphics-refresh behavior was changed. The build scope was not widened.

Validation includes restart/proof reuse, migration without duplicate jobs,
direction-specific transfers and a free-agent gap, unknown-structure no-AI/no-DLL
behavior, source-change waits, invalid historical evidence, unverified fourth
subteams, and applying an already rendered image while preserving unrelated
PNG/XML records. Original saves are not rewritten. Full real-file decoding and
ingestion were also run without a game process: 95,386 players, 47,155 teams,
20.139 seconds read and 1.484 seconds ingest on this Linux cloud host. All 154
role observations across the two native reports (147 distinct teams) agree with
the existing classifier, including its unknown-owner cases.

The same host's pre-change source read measured 17.428 seconds / 768.9 MiB peak
RSS; the new full read/ingest process peaked at 793.4 MiB. These are process
measurements, not Windows app benchmarks or proof of bounded whole-app RAM.
The new path removes subsequent live team-query waits; it does not eliminate
save decompression/player parsing. Windows EXE build and integrated Windows app
execution remain unverified here. Synthetic transfers and paid-image reuse tests
are separate from the user's actual native-report evidence.
The shared table also records its own source stamp, so updating a baseline with
an older app cannot make stale team data appear current. The final Python suite
passed 435 tests, including this cache-stamp regression and malformed optional
metadata handling. No additional dependencies were introduced.

## Complete independent club report received 2026-11-23

The updated holdout run completed after 222.599 seconds. It records a transient
heartbeat wait but has no final error or unverified-results section, and has a
final query context for the managed team's session. This is actual Windows
evidence that the revised client can recover from a wait during a long run.

The report covers all planned 24 clubs / 75 distinct teams. Excluding the two
retained control clubs, 22 clubs / 68 teams are disjoint from the calibration
cohort at both club-ID and team-ID level. Its source SHA-256 matches the original
controlled first-team save and the independently generated local sample plan.

The received report's `matches` booleans were not taken on trust. A local read-only
assertion check reconstructed references again from the saved plan and verified:

- Every received team index, UID, storing club UID, type and first-team boolean.
- All seven properties for every sampled anchor, including valid null references:
  168 slots agree, of which **154 belong to the 22 previously unseen clubs**.
- All 525 repeated property observations returned through the 75 queried team
  rows also agree with their parent context. These are repeated observations,
  not 525 independent club-role relationships.
- All source rows and target sets agree with the local holdout plan; controls
  are the only overlap with the original cohort.

Across calibration and holdout this gives 47 clubs, 147 distinct queried teams
and 329 distinct anchor/property slots. There were no mismatches in either
cohort. Both cohorts are from the same career and game date. Types 22 and 37
still lack a separate holdout representative; other careers and unobserved flag
states are not established by these results.

Conclusion: the candidate's reconstruction of the tested native references has
passed the planned separate-club check. This does not itself assign squad labels
or integrate the reader into the app. In particular, generic container names and
a controlled B team's own `IsFirstTeam` boolean retain the contextual caveats
documented below. Production source/proof handling and arrival/departure scope
integration remain separate work. No app worker, DLL, game API or settings were
modified during this verification step. Raw user reports remain outside Git.

## Partial independent report and wait-budget correction 2026-11-23

The uploaded holdout report contains 52 of the planned 75 team responses from one
session/epoch/snapshot, but `native` is null and the run ended at its wait timeout.
All 52 received team UIDs, storing club UIDs and types match the saved sample.
Anchors are available for 18 clubs including the two controls: 16 genuinely new
club anchors supply 112 reference observations, all matching the frozen candidate.
This is encouraging independent **partial** evidence, not a completed coherent
holdout result: final connection/context checks and six new club anchors are
still missing. It must not enable production classification.

Review found a client-side timing defect: the 120-second transient-wait deadline
started before the entire multi-batch resolve, so successful query time consumed
the budget too. A slow run could therefore time out on its first transient wait,
even after making substantial progress. This defect is reproduced synthetically;
the uploaded report did not capture enough timing/last-wait detail to establish
that it explains the actual interruption completely.

The diagnostic now resets its no-progress wait baseline when additional cache
keys appear. This only tracks progress; actual reuse still requires the existing
session/epoch/snapshot and final managed-club/freshness checks. It retains a
ten-minute total retry budget, preserves permanent-error handling, and records
`last_wait_reason` and `query_elapsed_seconds`. Native requests retain their own
bounded waits and cleanup; no request is forced through a busy game.

Regressions cover a 130-second successful partial collection followed by a brief
wait and recovery, unchanged-cache timeout, and repeated new epochs eventually
exhausting the total retry budget. No DLL, game API, app worker or classification
rule was modified. Actual Windows recovery and the remaining independent samples
still need an updated diagnostic run.
The focused Python suite passed 65 tests. All 52 partial observations were also
checked against the locally generated holdout plan, including its source hash.

## Complete native calibration and independent sample plan 2026-11-23

The second uploaded report completed: 25 clubs, 79 distinct team rows, no error
or unverified-results section, and a final query context. Every team UID, storing
club UID and `TeamType` agrees with the matching controlled first-team save.
Seventeen distinct type values are covered; all 30 native `IsFirstTeam=True`
rows have type 0 and the remaining 49 have nonzero types. The physical loaded
filename remains operator-confirmed rather than exposed by the service.

Important semantic observations:

- Barcelona B is its storing club's first team, but not the parent's
  `Club.ReservesTeam`; it is the parent's second generic youth-container entry.
- The generic highest container also selects explicit reserve teams. Likewise,
  `Club.YouthTeam3` can select a controlled club's own main team. These property
  names alone must not become squad labels.
- The same type 1, 9 or 16 can have an explicit reserve reference in one club and
  no matching reference in another. The type alone is insufficient.

The counted team reader now exposes the club record's prefix flags separately
from its tail flag. A research-only `candidate_references()` uses the observed
type sets, the prefix's low bit, and the parent's ordered own/controlled team list
to reconstruct references. It excludes the parent's identity anchor, not every
type-0 child. It does not read age, contracts or player slots to classify teams.
Unsupported type/flag shapes raise rather than receive a guessed role.

This candidate matches all 175 distinct anchor-property slots (25 clubs x 7
properties), and all 553 observations when the same properties returned through
the 79 team rows are included. **This is fitting/reconstruction against the data
used to derive the rule, not independent validation.** The low bit's full meaning
and behavior in other structures/careers remain unverified. It must not replace
the production classifier on these results alone.

The diagnostic now has `--holdout` mode and records candidate/native comparisons
without replacing either. Besides the two control clubs, it excludes every
original sample club and every previously queried team. The provided first-team
save selects 22 new clubs / 68 new teams (24 clubs / 75 teams including controls).
They cover 25 of the original 27 type/flag/control-link combinations independently;
types 22 and 37 in their observed shapes lack a separate representative. They
remain unvalidated by the holdout even if all other comparisons pass.

Synthetic regressions cover prefix/tail flag separation, generic containers
containing controlled main teams, low-bit candidate behavior, unknown shapes,
nonoverlapping holdout selection and retaining contradictory native evidence.
No native API, DLL, paid generation, support profile, or production app behavior
changed. Actual holdout responses are the next required independent evidence;
the existing saves need not be uploaded again.
The focused Python run passed 63 tests. A fresh read of the original `.fm` file
reproduced all 175 anchor comparisons, and the generated holdout plan was checked
for both club and team disjointness outside the retained controls.

## Partial native comparison received 2026-11-23

The uploaded `save-team-roles.json` identifies the supplied first-team save by its
previously verified SHA-256. It has `native: null` and an error corresponding to
`TeamReader.connection()` finding no fresh session heartbeat, with stale-session
evidence present. This does not identify whether the game exited, paused updates,
or stopped responding; no actual game crash or corrupted team data is established.

The report retains 20 cached responses from one session/epoch/snapshot. Each has
matching saved/native team UID, storing club UID, and type value, with no recorded
row or cleanup error. Observed raw types are 0, 1, 3, 11, 12, 14, 16, 17 and 18.
These are partial observations: final freshness/context and managed-club proof
did not complete, so the report is not a verified 79-team comparison and cannot
enable a global classifier.

One useful observed distinction: the type-3 examples are selected by a highest
youth-container property without an explicit matching `Club.ReservesTeam`.
The reserve and youth-container references can also overlap, as already seen
for Manchester United. Neither a type number nor a generic container's name is
an independent replacement for the explicit club-role evidence.

The one-time client previously propagated any `GameWait` straight to an error
report. It now retries only that transient exception with a 120-second budget,
preserving the same `TeamReader` instance. Its existing cache keys and final
freshness checks control reuse; no old report is imported as a cache. Nontransient
errors still stop immediately, and timeout retains unverified observations.
The managed/control clubs are queried first without changing sample coverage.
No app worker, native API, profile/hash guard, or DLL was changed.

Regressions exercise transient recovery, bounded timeout, permanent-error
propagation, and sample priority. A transport test with the real `TeamReader`
receives one batch, simulates a stale heartbeat during the next batch, restores
the heartbeat and verifies that only the missing teams are requested, with a
fresh final context required. Actual Windows recovery and the remaining team
relationships still need the updated diagnostic run.
The focused Python suite passed 58 tests. Re-reading the actual first-team save
confirmed the same source hash and 79-target set, with both control clubs now
first in the query plan.

## Relationship survey and prepared native cross-check 2026-11-23

Across the parsed club catalog, all 21,445 clubs have exactly one own team whose
team unique ID equals that club's database unique ID. Each of these records has
raw type 0. This is a corpus-wide identity observation, not a substitute for the
game's `IsFirstTeam` property; a separately stored B club has its own such team.

The catalog contains 736 controlled-team entries. Of these, 734 have raw type 0,
but two have raw type 11, the same candidate type as the user-confirmed Barcelona
U19. That does not independently confirm those two teams' roles, but rules out
treating a controlled-team link as sufficient evidence of a universally identical
storage shape. The full table contains 35 raw type values. Neither age-like
values, names, a slot, nor a type code is used to assign a squad role.

Further semantic verification needs independent native relationships, which the
cloud environment cannot obtain from an unconnected Windows game. Prepared
`verify_save_team_roles.bat` / `scripts/verify_save_team_roles.py` to make that
comparison in one run using the existing DLL and `TeamReader`. It selects one
club per observed raw-type/flag/control-link combination, includes the previously
observed control clubs and the save's managed club, then reads all listed teams
of those clubs. Each provided save yields 25 clubs and 79 unique team targets,
covering 27 observed combinations. The plan is bounded to 256 targets; requests
retain the existing four-team batch size and native cleanup/state guards.

The tool checks every returned team UID and storing club UID against the save.
For each parent club, its matching-identity anchor must have native
`IsFirstTeam=True`. It records actual parent reserve/youth reference matches
separately from each child's own boolean, preserving both when a B team is its
own club's first team. It does not infer a role or change the app classifier.
Native `TeamType` agreement is reported as a comparison, not assumed.

Source reads completed against all three real saves, including stable-copy and
managed-club checks. Fake-reader tests cover controlled-team owner separation,
parent references, differing sampled shapes, bad/missing identities, cleanup
errors, malformed refs, busy-state propagation and request bounds. Actual Windows
native results remain pending. Team UID/managed-club proofs cannot verify a
physical loaded-save filename/hash; the report explicitly marks that limitation.
Failed runs retain partial service observations separately as unverified data,
never as completed comparisons. The focused Python run passed 54 tests across
the new comparison/probe and existing squad diagnostic/classifier/team reader.

Run instructions: [세이브·게임 팀 참조 대조](save-team-role-verification.ko.md).
No native API, DLL, supported build range, paid generation, or production app
behavior was changed. This tool is a source-checkout diagnostic, not an installer
or a new end-user app feature.

## Counted team-table verification 2026-11-23

Added the isolated research reader `scripts/probe_save_teams.py`; the app does not
import it. It accepts decompressed bytes only for the observed save build
`27.1.0+2505117`, walks a declared record count, checks every ordinal footer and
distinct team unique ID, reads variable roster/name lengths, and requires every
supplied club-team ownership reference to agree. Missing, conflicting, damaged,
or ambiguous tables raise an error. It returns raw fields, never squad labels.
The synthetic regression fixture contains no real save fragments or identities.

All three actual `.fm` saves were opened sequentially with the pinned reader in
strict mode. Club checks were enforced with `save.clubs()`, then ownership was
taken directly from its club index. The counted research reader reached all
55,063 team records, including the last record, and matched all 47,155 own-team
club references. This supersedes the earlier 44,337-candidate scan and its 2,818
unmatched entries. Explicitly named teams were one cause of those misses: two
variable-length names sit between the ownership field and the identity footer.
The national-team variant also has a counted optional prefix array. The old byte
after a footer belongs to the following record; the walk now identifies each
record's own variant at its start instead.

The three tables have identical team identity, owner, raw type, national marker,
raw flag, and name fields. Their roster counts change only as follows:

| Assigned save | Main team 540 | Reserve 28346 | Youth 28347 |
|---|---:|---:|---:|
| First team | 24 | 37 | 17 |
| Reserve | 22 | 39 | 17 |
| Youth | 22 | 37 | 19 |

Exactly the source and destination counts change by two in each move; total
stored roster entries stay at 98,440. This independently supports the record
boundaries and roster-count interpretation. It does not prove every roster entry
is a distinct player across all teams.

The nearby raw flag cannot be used directly as `IsFirstTeam`: the native-confirmed
Manchester United main team has flag 0 and its youth team has flag 1, opposite
to the native boolean. Inverting it is also not established. The explicitly
named Bayern U19 record has the same candidate type 11 as user-confirmed Barcelona
U19, but flag 0 rather than 1. Overall 1,597 nonzero-type records also have flag 0.
These are reasons to investigate the flag, not independent in-game confirmations
of those other teams' roles. Its exact meaning remains unknown; the parser
intentionally does not interpret it.

Verification includes synthetic tests for named UTF-8 teams, national prefix
extensions, changed roster lengths, native owner index zero, mismatched owners,
truncation, corrupt lengths/counts/footer ordinals, duplicate IDs, ambiguous
tables, wrong builds, and national/club ownership collisions. Real-save inspection
scripts and extracted records stay outside Git. Parsing an already decompressed
section took about 1.1–1.2 seconds here; this excludes decompression/player reads
and is not an app lookup-time or Windows benchmark.

The focused Python run passed 40 tests covering this probe, the existing save
assignment diagnostic, and the existing squad classifier. The app's full GUI,
native runtime, and paid image-generation tests were not rerun for this isolated
research module.

Remaining blocker: complete framing and ownership are now demonstrated on this
career, but these fields still do not establish the saved equivalents of the
game's `IsFirstTeam`, `Club.ReservesTeam`, and explicit youth relationships. No
native lookup was removed and no unverified numeric/age/slot classifier was
enabled. These are three snapshots of one career, not three independent careers.

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
