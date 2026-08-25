"""Browser-free tests for the shape of a solved response.

Covers the things that are easy to break silently: the /v1 payload for an
ordinary HTML solve must stay byte-identical to FlareSolverr's (no extra keys),
a non-HTML document must survive the trip through the passthrough as bytes,
cookies must look the same whichever engine solved the request, and the cookies
must be read after waitInSeconds rather than before it.

Run: PYTHONPATH=src uv run --no-project python -m unittest test_response_shape
"""
import base64
import unittest
from unittest.mock import patch

import flaresolverr_service
import passthrough
import utils
from dtos import STATUS_OK, V1RequestBase, V1ResponseBase
from engines.base import SolveResult
from engines.chrome_engine import ChromeEngine
from engines.stealth_engine import _to_client_cookies, _to_playwright_cookies

PDF_BYTES = b"%PDF-1.4 fake document"

PLAYWRIGHT_COOKIE = {"name": "cf_clearance", "value": "abc", "domain": ".example.tld",
                     "path": "/", "expires": 1893456000.5, "httpOnly": True,
                     "secure": True, "sameSite": "None"}
SELENIUM_COOKIE = {"name": "cf_clearance", "value": "abc", "domain": ".example.tld",
                   "path": "/", "expiry": 1893456000, "httpOnly": True, "secure": True}


def _serialized(result: SolveResult) -> dict:
    return utils.object_to_dict(flaresolverr_service._to_challenge_resolution(result))['result']


def _solver_response(response: str, content_type: str = None) -> V1ResponseBase:
    solution = {"url": "https://example.tld/doc", "status": 200, "response": response}
    if content_type is not None:
        solution["contentType"] = content_type
    return V1ResponseBase({"status": STATUS_OK, "solution": solution})


class HtmlResponseShapeTest(unittest.TestCase):

    def test_html_solve_omits_content_type(self):
        self.assertNotIn('contentType', _serialized(SolveResult(response="<html/>")))


class PdfResponseShapeTest(unittest.TestCase):

    def test_pdf_solve_reports_its_content_type(self):
        result = SolveResult(response="ZmFrZQ==", content_type="application/pdf")
        self.assertEqual(_serialized(result)['contentType'], "application/pdf")


class PassthroughBodyTest(unittest.TestCase):

    def test_pdf_solution_is_served_as_raw_bytes(self):
        encoded = base64.b64encode(PDF_BYTES).decode("ascii")
        with patch.object(flaresolverr_service, 'controller_v1_endpoint',
                          return_value=_solver_response(encoded, "application/pdf")):
            _status, body, _content_type, _solution = passthrough._solve("https://example.tld/doc")
        self.assertEqual(body, PDF_BYTES)

    def test_pdf_solution_is_served_under_its_content_type(self):
        encoded = base64.b64encode(PDF_BYTES).decode("ascii")
        with patch.object(flaresolverr_service, 'controller_v1_endpoint',
                          return_value=_solver_response(encoded, "application/pdf")):
            _status, _body, content_type, _solution = passthrough._solve("https://example.tld/doc")
        self.assertEqual(content_type, "application/pdf")

    def test_html_solution_stays_html(self):
        with patch.object(flaresolverr_service, 'controller_v1_endpoint',
                          return_value=_solver_response("<html/>")):
            _status, _body, content_type, _solution = passthrough._solve("https://example.tld/page")
        self.assertEqual(content_type, passthrough._HTML_CONTENT_TYPE)


class CookieShapeTest(unittest.TestCase):

    def test_returned_cookie_uses_the_selenium_expiry_key(self):
        self.assertEqual(_to_client_cookies([PLAYWRIGHT_COOKIE])[0]['expiry'], 1893456000)

    def test_returned_cookie_drops_the_playwright_expires_key(self):
        self.assertNotIn('expires', _to_client_cookies([PLAYWRIGHT_COOKIE])[0])

    def test_session_cookie_is_returned_without_an_expiry(self):
        session_cookie = dict(PLAYWRIGHT_COOKIE, expires=-1)
        self.assertNotIn('expiry', _to_client_cookies([session_cookie])[0])

    def test_client_cookie_expiry_is_translated_for_playwright(self):
        self.assertEqual(_to_playwright_cookies([SELENIUM_COOKIE])[0]['expires'], 1893456000.0)

    def test_client_cookie_drops_keys_playwright_rejects(self):
        self.assertNotIn('expiry', _to_playwright_cookies([SELENIUM_COOKIE])[0])


class _FakeDriver:
    """The slice of the Selenium API an unchallenged solve touches.

    Its cookie jar changes while waitInSeconds runs, which is what makes the
    ordering observable: read the jar too early and the late cookie is missing.
    """

    def __init__(self):
        self.title = "Example"
        self.current_url = "https://example.tld/"
        self.page_source = "<html/>"
        self.waited = False

    def get(self, url):
        pass

    def find_element(self, *args):
        return object()

    def find_elements(self, *args):
        return []

    def get_cookies(self):
        jar = [{"name": "early", "value": "1"}]
        if self.waited:
            jar.append({"name": "late", "value": "1"})
        return jar


class CookieCaptureTimingTest(unittest.TestCase):
    """A page that sets a cookie from its own JS does it during waitInSeconds."""

    def _solve(self, **req_fields):
        driver = _FakeDriver()
        # disableMedia is pinned so an ambient DISABLE_MEDIA cannot send the
        # solve down the CDP branch this fake driver does not implement.
        fields = {"url": "https://example.tld/", "waitInSeconds": 1, "disableMedia": False}
        fields.update(req_fields)

        def _wait(_seconds):
            driver.waited = True

        with patch('engines.chrome_engine.time.sleep', side_effect=_wait), \
                patch.object(utils, 'get_user_agent', return_value="ua"):
            return ChromeEngine(sessions=None)._evil_logic(V1RequestBase(fields), driver, "GET")

    def test_cookies_set_during_the_wait_are_returned(self):
        names = [c["name"] for c in self._solve().cookies]
        self.assertIn("late", names)

    def test_cookies_are_returned_when_only_cookies_were_asked_for(self):
        names = [c["name"] for c in self._solve(returnOnlyCookies=True).cookies]
        self.assertEqual(names, ["early"])


if __name__ == '__main__':
    unittest.main()
