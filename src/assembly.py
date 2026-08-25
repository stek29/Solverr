"""The one place a solved response is assembled, for both engines.

Both engines used to build their own `SolveResult`, in the same order, from the
same request options. Writing that order twice is what let the same defect land
in both at once: each read the cookie jar before `waitInSeconds` rather than
after, so a page that set a cookie from its own JavaScript was handed back with
a cookie list that did not have it.

The order cannot simply be lifted into a shared function, because one engine is
synchronous (Selenium, on the request thread) and the other is asynchronous
(Playwright, on the shared event loop), and one function body cannot be both.
So the order is a generator that says *what* to read and in *what* order, and
each engine supplies only *how* to read it. That is the whole engine-specific
part, a flat mapping with no rules in it, and neither engine can reorder the
reads without editing this file.

The rules pinned here, all of which a client can observe:

- `status` is 200 whenever a page came back. Clients reject non-2xx, and a
  Cloudflare 403 challenge page is a solve outcome rather than a solve failure;
  a real block is raised as an error by the denied detection before this runs.
- `headers` is absent entirely under `returnOnlyCookies`, and otherwise comes
  from the engine: the real response headers when RESPONSE_HEADERS is on, an
  empty map when it is off. Both engines answer the same question the same way,
  so a client cannot tell which one solved its request.
- The wait happens before the body is read, which is the point of asking for it.
- **The cookie jar is read last**, after the wait and after everything else.
- The screenshot is opt-in and is encoded here, so both engines hand over raw
  bytes and only one of them decides what the field looks like.
"""
import base64
import logging
from enum import Enum, auto

from engines.base import SolveResult


class Read(Enum):
    """A value only the engine can fetch. The order they appear in is the rule."""
    URL = auto()
    USER_AGENT = auto()
    TOKEN = auto()
    WAIT = auto()
    HEADERS = auto()       # the page's response headers, or {} when off
    BODY = auto()          # (text, content_type or None)
    SCREENSHOT = auto()    # raw bytes
    COOKIES = auto()       # already in the client's dialect


def assembly(req, message: str):
    """Yield each read in the order it must happen, and build the result from it.

    Driven by `run` or `run_async` below rather than called directly.
    """
    result = SolveResult()
    result.status = 200
    result.message = message
    result.url = yield Read.URL
    result.user_agent = yield Read.USER_AGENT
    result.turnstile_token = yield Read.TOKEN

    if not req.returnOnlyCookies:
        result.headers = yield Read.HEADERS
        if req.waitInSeconds and req.waitInSeconds > 0:
            logging.info("Waiting %s seconds before returning the response...", req.waitInSeconds)
            yield Read.WAIT
        result.response, result.content_type = yield Read.BODY

    if req.returnScreenshot:
        result.screenshot = base64.b64encode((yield Read.SCREENSHOT)).decode("ascii")

    # Last, after the wait: a page that sets cookies from its own JavaScript
    # does it during that wait, and reading earlier handed back the body that
    # has them beside a cookie list that does not.
    result.cookies = yield Read.COOKIES
    return result


def run(req, message: str, reads: dict) -> SolveResult:
    """Drive the assembly where every read is synchronous."""
    generator = assembly(req, message)
    try:
        step = next(generator)
        while True:
            step = generator.send(reads[step]())
    except StopIteration as done:
        return done.value


async def run_async(req, message: str, reads: dict) -> SolveResult:
    """Drive the same assembly where every read is awaitable."""
    generator = assembly(req, message)
    try:
        step = next(generator)
        while True:
            step = generator.send(await reads[step]())
    except StopIteration as done:
        return done.value
