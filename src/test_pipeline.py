"""The verdict rule, tested without either engine.

pipeline.verdict is a generator, so what it looks at and in what order can be
recorded directly, with no browser and no engine. The short-circuiting matters
as much as the answer: the stealth engine re-runs this on every poll while a
challenge is up, and each selector costs a round trip.

Run: PYTHONPATH=src uv run --no-project python -m unittest test_pipeline
"""
import unittest

import pipeline
from detection import (ACCESS_DENIED_SELECTORS, ACCESS_DENIED_TITLES,
                       CHALLENGE_SELECTORS, CHALLENGE_TITLES, TURNSTILE_SELECTORS)
from pipeline import Look, Verdict


def decide(title="Example", present=(), *, turnstile_is_a_challenge=True):
    """Run the rule, returning (verdict, is_turnstile, reason, selectors looked at)."""
    looked = []

    def selector(sel):
        looked.append(sel)
        return sel in present

    found, is_turnstile, reason = pipeline.run(
        {Look.TITLE: lambda _a: title, Look.SELECTOR: selector},
        turnstile_is_a_challenge=turnstile_is_a_challenge)
    return found, is_turnstile, reason, looked


class VerdictTest(unittest.TestCase):

    def test_a_plain_page_is_nothing(self):
        self.assertEqual(decide()[0], Verdict.NONE)

    def test_a_denied_title_is_denied(self):
        self.assertEqual(decide(title=ACCESS_DENIED_TITLES[0])[0], Verdict.DENIED)

    def test_a_denied_title_matches_on_a_prefix(self):
        # startswith, not equality: upstream's list is prefixes.
        self.assertEqual(decide(title=ACCESS_DENIED_TITLES[0] + " - example")[0], Verdict.DENIED)

    def test_a_denied_selector_is_denied(self):
        self.assertEqual(decide(present={ACCESS_DENIED_SELECTORS[0]})[0], Verdict.DENIED)

    def test_a_challenge_title_is_a_challenge(self):
        self.assertEqual(decide(title=CHALLENGE_TITLES[0])[0], Verdict.CHALLENGE)

    def test_a_challenge_title_matches_regardless_of_case(self):
        self.assertEqual(decide(title=CHALLENGE_TITLES[0].upper())[0], Verdict.CHALLENGE)

    def test_a_challenge_title_does_not_match_on_a_prefix(self):
        # Equality, not startswith: these are exact titles, unlike the denied list.
        self.assertEqual(decide(title=CHALLENGE_TITLES[0] + " more")[0], Verdict.NONE)

    def test_a_challenge_selector_is_a_challenge(self):
        self.assertEqual(decide(present={CHALLENGE_SELECTORS[0]})[0], Verdict.CHALLENGE)

    def test_denied_wins_over_a_challenge(self):
        found, _t, _r, _l = decide(title=ACCESS_DENIED_TITLES[0],
                                   present={CHALLENGE_SELECTORS[0]})
        self.assertEqual(found, Verdict.DENIED)


class TurnstileCapabilityTest(unittest.TestCase):
    """The one difference between the engines is a parameter, not a fork."""

    def test_a_widget_is_a_challenge_when_the_engine_can_click_it(self):
        found, _t, _r, _l = decide(present=set(TURNSTILE_SELECTORS),
                                   turnstile_is_a_challenge=True)
        self.assertEqual(found, Verdict.CHALLENGE)

    def test_a_widget_is_not_a_challenge_when_the_engine_cannot(self):
        found, _t, _r, _l = decide(present=set(TURNSTILE_SELECTORS),
                                   turnstile_is_a_challenge=False)
        self.assertEqual(found, Verdict.NONE)

    def test_a_widget_is_reported_to_the_engine_that_can_click_it(self):
        _f, is_turnstile, _r, _l = decide(present=set(TURNSTILE_SELECTORS),
                                          turnstile_is_a_challenge=True)
        self.assertTrue(is_turnstile)

    def test_an_engine_that_cannot_click_one_is_not_asked_to_look(self):
        # Each selector is a round trip, so an answer nobody uses is not fetched.
        looked = decide(present=set(TURNSTILE_SELECTORS),
                        turnstile_is_a_challenge=False)[3]
        self.assertNotIn(TURNSTILE_SELECTORS[0], looked)


class ShortCircuitTest(unittest.TestCase):
    """Each selector is a round trip, so the rule stops as soon as it knows."""

    def test_a_denied_title_looks_at_no_selectors_at_all(self):
        self.assertEqual(decide(title=ACCESS_DENIED_TITLES[0])[3], [])

    def test_a_denied_selector_stops_at_the_one_that_matched(self):
        self.assertEqual(decide(present={ACCESS_DENIED_SELECTORS[0]})[3],
                         [ACCESS_DENIED_SELECTORS[0]])

    def test_a_clean_page_looks_at_every_list_once(self):
        looked = decide()[3]
        self.assertEqual(len(looked), len(set(looked)), "a selector was tested twice")

    def test_a_challenge_title_skips_the_challenge_selectors(self):
        looked = decide(title=CHALLENGE_TITLES[0])[3]
        self.assertNotIn(CHALLENGE_SELECTORS[0], looked)


if __name__ == '__main__':
    unittest.main()
