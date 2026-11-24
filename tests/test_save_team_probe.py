import struct
import unittest

from scripts.probe_save_teams import BUILD, candidate_references, read_team_table


def record(ordinal, owner=7, *, national=False, extra=0, names=('', ''),
           roster=(), raw_type=0, raw_flag=0, uid=None, flags=0):
    # Synthetic counted record; no real save bytes or game identities.
    if national:
        prefix = bytearray(88 + 10 * extra)
        prefix[0], prefix[54] = 11, extra
    else:
        prefix = bytearray(34)
        prefix[0] = 10
        prefix[1] = flags
    players = struct.pack('<H', len(roster)) + b''.join(struct.pack('<I', p) for p in roster)
    tail = bytes(18) + bytes((raw_type, int(national), raw_flag, 100, 255, 0))
    tail += struct.pack('<I', owner)
    text = b''.join(struct.pack('<I', len(n.encode())) + n.encode() + b'\x00' for n in names)
    return bytes(prefix) + players + tail + text + struct.pack('<III', ordinal, uid or 700 + ordinal, 900 + ordinal)


def table(*rows):
    return struct.pack('<IB', len(rows), 0) + b''.join(rows)


class SaveTeamProbeTests(unittest.TestCase):
    def test_walks_named_teams_national_extensions_and_all_roster_lengths(self):
        data = table(record(0, national=True, extra=2, roster=(31, 32)),
                     record(1, owner=0, names=('Northbridge U19', '노스브리지'),
                            raw_type=11, raw_flag=0, roster=(41,)),
                     record(2, owner=8, raw_type=0, roster=()))
        result = read_team_table(b'unrelated prefix' + data + b'trailer', BUILD, {1: 0, 2: 8})
        rows = result['records']
        self.assertEqual(result['header'], len(b'unrelated prefix'))
        self.assertEqual(result['end'], len(b'unrelated prefix') + len(data))
        self.assertEqual(rows[1]['names'], ('Northbridge U19', '노스브리지'))
        self.assertEqual([r['roster_count'] for r in rows], [2, 1, 0])
        self.assertEqual(rows[1]['raw_type'], 11)
        self.assertEqual(rows[1]['raw_flag'], 0)
        self.assertFalse(any('kind' in r or 'is_first_team' in r for r in rows))

    def test_changing_roster_size_moves_footer_but_preserves_team_fields(self):
        first = read_team_table(table(record(0, roster=(41, 42))), BUILD, {0: 7})['records'][0]
        second = read_team_table(table(record(0, roster=())), BUILD, {0: 7})['records'][0]
        self.assertEqual(first['footer'] - second['footer'], 8)
        for field in ('team_id', 'unique_id', 'owner_index', 'raw_type', 'raw_flag'):
            self.assertEqual(first[field], second[field])

    def test_owner_links_are_required_for_every_known_team(self):
        data = table(record(0), record(1, owner=8))
        for owners in ({0: 7, 1: 9}, {2: 7}, {}, {0: True}):
            with self.subTest(owners=owners), self.assertRaises(ValueError):
                read_team_table(data, BUILD, owners)

    def test_rejects_truncated_records_broken_names_counts_and_footers(self):
        original = table(record(0, names=('Northbridge', 'North')))
        mutations = [original[:-1], original[:40], original[:5]]
        wrong_footer = bytearray(original)
        struct.pack_into('<I', wrong_footer, len(original) - 12, 1)
        mutations.append(wrong_footer)
        wrong_roster = bytearray(original)
        struct.pack_into('<H', wrong_roster, 5 + 34, 65535)
        mutations.append(wrong_roster)
        wrong_count = bytearray(original)
        struct.pack_into('<I', wrong_count, 0, 2)
        mutations.append(wrong_count)
        broken_name = bytearray(original)
        broken_name[5 + 36 + 28 + 4 + len('Northbridge')] = 1
        mutations.append(broken_name)
        oversized_name = bytearray(original)
        struct.pack_into('<I', oversized_name, 5 + 36 + 28, 0xffffffff)
        mutations.append(oversized_name)
        for index, data in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(ValueError):
                read_team_table(bytes(data), BUILD, {0: 7})

    def test_rejects_duplicate_identity_and_ambiguous_tables(self):
        duplicate = table(record(0, uid=700), record(1, uid=700))
        one = table(record(0))
        for data in (duplicate, one + one):
            with self.subTest(length=len(data)), self.assertRaises(ValueError):
                read_team_table(data, BUILD, {0: 7})

    def test_patch_build_uses_same_strict_framing_and_owner_validation(self):
        data = table(record(0))
        result = read_team_table(data, '27.1.1+2511875', {0: 7})
        self.assertEqual(result['records'][0]['team_id'], 0)
        with self.assertRaises(ValueError):
            read_team_table(data, '27.1.1+2511875', {0: 8})
        with self.assertRaises(ValueError):
            read_team_table(data[:-1], '27.1.1+2511875', {0: 7})

    def test_rejects_other_builds_and_national_club_owner_collisions(self):
        for data, build in ((table(record(0)), 'unverified'),
                            (table(record(0, national=True)), BUILD)):
            with self.subTest(build=build), self.assertRaises(ValueError):
                read_team_table(data, build, {0: 7})

    def test_keeps_prefix_flags_separate_from_tail_flag(self):
        data = table(record(0, flags=21, raw_flag=1))
        row = read_team_table(data, BUILD, {0: 7})['records'][0]
        self.assertEqual((row['raw_flags'], row['raw_flag']), (21, 1))

    def test_candidate_preserves_controlled_first_team_in_generic_container(self):
        def row(tid, typ, flags=0):
            return dict(team_id=tid, raw_type=typ, raw_national=0, raw_flags=flags)
        club = dict(anchor_team_id=10, teams=[row(10, 0), row(11, 1, 1),
                    row(12, 11), row(13, 0), row(14, 0)])
        predicted = candidate_references(club)
        self.assertIsNone(predicted['Club.ReservesTeam'])
        self.assertEqual(predicted['Club.YouthTeam'], 12)
        self.assertEqual(predicted['TeamContainer.HighestLevelYouthTeam'], 12)
        self.assertEqual(predicted['TeamContainer.SecondHighestLevelYouthTeam'], 13)
        self.assertEqual(predicted['Club.YouthTeam3'], 14)
        self.assertFalse(any(key in predicted for key in ('kind', 'is_first_team')))
        club['teams'][1]['raw_flags'] = 0
        self.assertEqual(candidate_references(club)['Club.ReservesTeam'], 11)

    def test_candidate_rejects_unobserved_shapes_instead_of_guessing_roles(self):
        original = dict(team_id=0, raw_type=0, raw_national=0, raw_flags=0)
        for changes in ({'raw_type': 255}, {'raw_type': True}, {'raw_flags': None},
                        {'raw_national': 1}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                candidate_references(dict(anchor_team_id=0, teams=[original | changes]))


if __name__ == '__main__':
    unittest.main()
