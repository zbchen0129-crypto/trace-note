import unittest
from eval.cross_context import CASES, payload_for, score


class CrossContextScoringTests(unittest.TestCase):
    def output(self, stance, source):
        return {'annotations': [{'labelId': 'livingStandard', 'stance': stance, 'stanceParagraphId': source}]}

    def test_incomplete_views_are_identical_and_do_not_require_hidden_stance(self):
        self.assertEqual(payload_for(CASES[0], 'adjacent'), payload_for(CASES[1], 'adjacent'))
        for case in CASES:
            self.assertTrue(score(case, 'adjacent', self.output('mentions', 'P001'))['matched'])
            self.assertFalse(score(case, 'adjacent', self.output(case['expected'], 'P004'))['matched'])

    def test_full_view_requires_correct_stance_and_remote_source(self):
        case = CASES[0]
        self.assertTrue(score(case, 'extra', self.output('opposes', 'P004'))['matched'])
        self.assertFalse(score(case, 'extra', self.output('supports', 'P004'))['matched'])
        self.assertFalse(score(case, 'extra', self.output('opposes', 'P001'))['matched'])
        self.assertFalse(score(case, 'extra', {'annotations': []})['matched'])
