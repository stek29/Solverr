"""One suite, both engines, for every rule that must hold identically.

The engines were written against each other rather than against a shared rule,
so the same defect landed in both at once: on 2026-08-25 both read the cookie
jar before `waitInSeconds` instead of after. A rule that must hold for both is
pinned once, and this is that pin for the rules no shared kernel covers yet.

Every test runs over both engines through `engine_fakes`, and reports which one
failed. Rules genuinely specific to one engine do not belong here: those are
capabilities, and they are tested where they live.

Run: PYTHONPATH=src uv run --no-project python -m unittest test_engine_conformance
"""
import base64
import unittest

from engine_fakes import HARNESSES, World


class EngineConformanceTest(unittest.TestCase):

    def each(self, **fields):
        """Yield (engine name, result) for the same world and request on both."""
        world = World()
        for harness in HARNESSES:
            yield harness.name, harness.solve(world, **fields), world

    # ---- the cookie jar is read last ---------------------------------------

    def test_cookies_set_during_the_wait_are_returned(self):
        # The defect that motivated this suite, in both engines at once.
        for name, result, _ in self.each(waitInSeconds=2):
            with self.subTest(engine=name):
                self.assertIn("late", [c["name"] for c in result.cookies])

    def test_cookies_are_returned_when_only_cookies_were_asked_for(self):
        for name, result, _ in self.each(returnOnlyCookies=True):
            with self.subTest(engine=name):
                self.assertEqual([c["name"] for c in result.cookies], ["early"])

    # ---- returnOnlyCookies drops exactly two things ------------------------

    def test_only_cookies_drops_the_body(self):
        for name, result, _ in self.each(returnOnlyCookies=True):
            with self.subTest(engine=name):
                self.assertIsNone(result.response)

    def test_only_cookies_drops_the_headers(self):
        for name, result, _ in self.each(returnOnlyCookies=True):
            with self.subTest(engine=name):
                self.assertIsNone(result.headers)

    # ---- an ordinary solve -------------------------------------------------

    def test_an_ordinary_solve_returns_the_page(self):
        for name, result, world in self.each():
            with self.subTest(engine=name):
                self.assertEqual(result.response, world.html)

    def test_an_ordinary_solve_reports_an_empty_header_map(self):
        # Neither engine reports real headers yet, and both say so the same way.
        for name, result, _ in self.each():
            with self.subTest(engine=name):
                self.assertEqual(result.headers, {})

    def test_an_ordinary_solve_reports_200(self):
        for name, result, _ in self.each():
            with self.subTest(engine=name):
                self.assertEqual(result.status, 200)

    def test_an_unchallenged_page_says_so(self):
        # The controller and the passthrough both key on this string.
        for name, result, _ in self.each():
            with self.subTest(engine=name):
                self.assertEqual(result.message, "Challenge not detected!")

    def test_html_carries_no_content_type(self):
        # Absent for HTML keeps the payload byte-identical to FlareSolverr's.
        for name, result, _ in self.each():
            with self.subTest(engine=name):
                self.assertIsNone(result.content_type)

    def test_the_user_agent_is_reported(self):
        for name, result, world in self.each():
            with self.subTest(engine=name):
                self.assertEqual(result.user_agent, world.user_agent)

    # ---- the screenshot is opt-in ------------------------------------------

    def test_no_screenshot_unless_asked(self):
        for name, result, _ in self.each():
            with self.subTest(engine=name):
                self.assertIsNone(result.screenshot)

    def test_a_screenshot_when_asked(self):
        for name, result, world in self.each(returnScreenshot=True):
            with self.subTest(engine=name):
                self.assertEqual(base64.b64decode(result.screenshot), world.screenshot)

    # ---- one cookie dialect reaches the client -----------------------------

    def test_a_returned_cookie_uses_the_selenium_expiry_key(self):
        # Playwright says "expires" as a float; a client must not be able to tell
        # which engine solved the request.
        for name, result, _ in self.each():
            with self.subTest(engine=name):
                early = [c for c in result.cookies if c["name"] == "early"][0]
                self.assertEqual(early["expiry"], 1893456000)

    def test_a_returned_cookie_never_carries_the_playwright_key(self):
        for name, result, _ in self.each():
            with self.subTest(engine=name):
                self.assertNotIn("expires", [k for c in result.cookies for k in c])

    def test_a_session_cookie_has_no_expiry_at_all(self):
        for name, result, _ in self.each(waitInSeconds=2):
            with self.subTest(engine=name):
                late = [c for c in result.cookies if c["name"] == "late"][0]
                self.assertNotIn("expiry", late)

    def test_both_engines_agree_on_the_cookie_key_set(self):
        seen = {}
        for name, result, _ in self.each():
            seen[name] = sorted({k for c in result.cookies for k in c})
        self.assertEqual(len(set(map(tuple, seen.values()))), 1, seen)


if __name__ == '__main__':
    unittest.main()
