import unittest

from transfer_types import TRANSFER_TYPES, classify_transfer, event_type
from scope_rules import migrate_scope, validate_scope


def person(club, loan, contract):
    return {'id':'1', 'identity':'same person', 'club_id':club, 'on_loan':loan, 'contract_club_id':contract}


class TransferTypeTests(unittest.TestCase):
    def test_observed_moves_distinguish_loans_returns_sales_and_free_signings(self):
        cases = [
            (person('10',False,'10'), person('20',True,'10'), 'loan'),
            (person('20',True,'10'), person('30',True,'10'), 'loan'),
            (person('20',True,'10'), person('10',False,'10'), 'loan_return'),
            (person('20',True,'10'), person('30',False,'30'), 'permanent'),
            (person('10',False,'10'), person('20',False,'20'), 'permanent'),
            (person('',None,''), person('20',False,'20'), 'permanent'),
        ]
        for before, after, kind in cases:
            with self.subTest(before=before, after=after):
                actual, reason = classify_transfer(before, after)
                self.assertEqual(actual, kind)
                self.assertTrue(reason)

    def test_missing_or_conflicting_evidence_is_never_guessed_as_a_permanent_move(self):
        cases = [
            (person('10',None,'10'), person('20',False,'20')),
            (person('20',True,''), person('10',False,'10')),
            (person('10',False,'10'), person('20',None,'20')),
            (person('10',False,'10'), person('20',False,'')),
            (person('10',False,'10'), person('20',True,'20')),
            (person('10',False,'10'), person('20',False,'30')),
            (person('10',False,'10'), person('20',False,'20') | {'identity':'new person'}),
        ]
        for before, after in cases:
            with self.subTest(before=before, after=after):
                self.assertEqual(classify_transfer(before, after)[0], 'unknown')

    def test_legacy_settings_include_every_type_without_sharing_mutable_defaults(self):
        first = migrate_scope({'all_players':True})
        self.assertEqual(first['transfer_types'], list(TRANSFER_TYPES))
        first['transfer_types'].clear()
        self.assertEqual(validate_scope({})['transfer_types'], list(TRANSFER_TYPES))

    def test_invalid_settings_are_rejected_and_empty_selection_is_allowed(self):
        for value in (None, True, 'loan', ['invented'], [False]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_scope({'transfer_types':value})
        self.assertEqual(validate_scope({'transfer_types':[]})['transfer_types'], [])

    def test_old_queued_moves_are_unknown_and_current_or_direct_requests_are_exempt(self):
        self.assertEqual(event_type({'club_id':'20','from_club_id':'10'}), 'unknown')
        self.assertIsNone(event_type({'club_id':'20'}))
        self.assertIsNone(event_type({'manual_request':True,'club_id':'20','transfer_type':'loan'}))
