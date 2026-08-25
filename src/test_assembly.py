"""The order a solved response is assembled in, tested without either engine.

assembly.assembly is a generator, so the order it reads things in can be
recorded directly, with no browser, no engine and no fake driver. That is what
makes the rule cheap enough to assert exhaustively.

Run: PYTHONPATH=src uv run --no-project python -m unittest test_assembly
"""
import base64
import unittest

import assembly
from assembly import Read
from dtos import V1RequestBase

VALUES = {
    Read.URL: "https://example-site.tld/",
    Read.USER_AGENT: "UA/1.0",
    Read.TOKEN: None,
    Read.WAIT: None,
    Read.BODY: ("<html/>", None),
    Read.SCREENSHOT: b"PNG",
    Read.COOKIES: [{"name": "a", "value": "1"}],
}


def drive(**fields):
    """Run the assembly, returning (result, the reads it asked for in order)."""
    order = []

    def record(step):
        def read():
            order.append(step)
            return VALUES[step]
        return read

    req = V1RequestBase(dict({"url": VALUES[Read.URL]}, **fields))
    result = assembly.run(req, "Challenge not detected!",
                          {step: record(step) for step in Read})
    return result, order


class AssemblyOrderTest(unittest.TestCase):

    def test_the_cookie_jar_is_read_last(self):
        # The defect this kernel exists to make unwritable.
        _result, order = drive(waitInSeconds=2)
        self.assertEqual(order[-1], Read.COOKIES)

    def test_the_cookie_jar_is_read_last_even_with_a_screenshot(self):
        _result, order = drive(waitInSeconds=2, returnScreenshot=True)
        self.assertEqual(order[-1], Read.COOKIES)

    def test_the_wait_happens_before_the_body_is_read(self):
        _result, order = drive(waitInSeconds=2)
        self.assertLess(order.index(Read.WAIT), order.index(Read.BODY))

    def test_no_wait_is_performed_when_none_was_asked_for(self):
        _result, order = drive()
        self.assertNotIn(Read.WAIT, order)

    def test_a_zero_wait_is_not_a_wait(self):
        _result, order = drive(waitInSeconds=0)
        self.assertNotIn(Read.WAIT, order)

    def test_only_cookies_reads_no_body(self):
        _result, order = drive(returnOnlyCookies=True, waitInSeconds=2)
        self.assertNotIn(Read.BODY, order)

    def test_only_cookies_does_not_wait_either(self):
        # The wait exists to let the body settle, so it is pointless without one.
        _result, order = drive(returnOnlyCookies=True, waitInSeconds=2)
        self.assertNotIn(Read.WAIT, order)

    def test_only_cookies_still_reads_the_jar(self):
        _result, order = drive(returnOnlyCookies=True)
        self.assertIn(Read.COOKIES, order)

    def test_no_screenshot_is_taken_unless_asked(self):
        _result, order = drive()
        self.assertNotIn(Read.SCREENSHOT, order)


class AssemblyResultTest(unittest.TestCase):

    def test_a_solved_page_reports_200(self):
        result, _ = drive()
        self.assertEqual(result.status, 200)

    def test_headers_are_an_empty_map(self):
        result, _ = drive()
        self.assertEqual(result.headers, {})

    def test_only_cookies_leaves_the_headers_unset(self):
        result, _ = drive(returnOnlyCookies=True)
        self.assertIsNone(result.headers)

    def test_only_cookies_leaves_the_body_unset(self):
        result, _ = drive(returnOnlyCookies=True)
        self.assertIsNone(result.response)

    def test_the_screenshot_is_base64_encoded_here(self):
        # Both engines hand over raw bytes so only one place decides the shape.
        result, _ = drive(returnScreenshot=True)
        self.assertEqual(base64.b64decode(result.screenshot), b"PNG")

    def test_a_content_type_from_the_body_read_reaches_the_result(self):
        order = []
        req = V1RequestBase({"url": VALUES[Read.URL]})
        reads = dict({step: (lambda s=step: VALUES[s]) for step in Read})
        reads[Read.BODY] = lambda: ("JVBERi0=", "application/pdf")
        result = assembly.run(req, "Challenge not detected!", reads)
        self.assertEqual(result.content_type, "application/pdf")

    def test_html_leaves_the_content_type_unset(self):
        result, _ = drive()
        self.assertIsNone(result.content_type)


if __name__ == '__main__':
    unittest.main()
