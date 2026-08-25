"""Browser-free fakes for driving either engine through the same assertions.

Not a test module (unittest discovers `test_*.py`), so it is imported rather
than collected. It exists because a rule that must hold for both engines is
pinned once, and the only way to pin one over both is to drive both.

Each harness takes the same `World`, a neutral description of what the browser
would find, and renders it in its own browser's dialect: Selenium cookies for
Chrome, Playwright cookies for stealth. That difference is deliberate, because
agreeing on the returned dialect is one of the rules being pinned.
"""
import asyncio
import base64
from dataclasses import dataclass, field
from unittest.mock import patch

from dtos import V1RequestBase
from engines.chrome_engine import ChromeEngine
from engines.stealth_engine import StealthEngine

# A cookie as the site would set it, before either browser's dialect is applied.
Cookie = tuple  # (name, value, expiry_epoch_or_None)

LOADED = [("early", "1", 1893456000)]
AFTER_WAIT = LOADED + [("late", "1", None)]


@dataclass
class World:
    """What the browser would find, described once for both engines."""
    title: str = "Example"
    html: str = "<html><body>ok</body></html>"
    url: str = "https://example-site.tld/"
    user_agent: str = "UA/1.0"
    screenshot: bytes = b"\x89PNG-bytes"
    cookies_at_load: list = field(default_factory=lambda: list(LOADED))
    cookies_after_wait: list = field(default_factory=lambda: list(AFTER_WAIT))


# ---- Chrome ----------------------------------------------------------------

class _SeleniumDriver:
    """The slice of the Selenium API an unchallenged solve touches."""

    def __init__(self, world: World):
        self._world = world
        self.waited = False
        self.title = world.title
        self.current_url = world.url
        self.page_source = world.html

    def get(self, _url):
        pass

    def delete_cookie(self, _name):
        pass

    def add_cookie(self, _cookie):
        pass

    def execute_script(self, _script):
        pass

    def execute_cdp_cmd(self, _cmd, _params):
        pass

    def find_element(self, *_args):
        return object()

    def find_elements(self, *_args):
        return []

    def get_screenshot_as_base64(self):
        return base64.b64encode(self._world.screenshot).decode("ascii")

    def get_cookies(self):
        source = self._world.cookies_after_wait if self.waited else self._world.cookies_at_load
        out = []
        for name, value, expiry in source:
            cookie = {"name": name, "value": value, "domain": ".example-site.tld",
                      "path": "/", "httpOnly": False, "secure": True}
            if expiry is not None:
                cookie["expiry"] = expiry
            out.append(cookie)
        return out


class ChromeHarness:
    name = "chrome"

    def solve(self, world: World, **fields):
        driver = _SeleniumDriver(world)
        req = V1RequestBase(dict({"url": world.url, "disableMedia": False}, **fields))

        def _slept(_seconds):
            driver.waited = True

        import utils
        with patch('engines.chrome_engine.time.sleep', side_effect=_slept), \
                patch.object(utils, 'get_user_agent', return_value=world.user_agent):
            return ChromeEngine(sessions=None)._evil_logic(req, driver, "GET", 60.0)


# ---- Stealth ---------------------------------------------------------------

class _PlaywrightContext:
    def __init__(self, page):
        self._page = page

    async def cookies(self):
        source = (self._page.world.cookies_after_wait if self._page.waited
                  else self._page.world.cookies_at_load)
        out = []
        for name, value, expiry in source:
            out.append({"name": name, "value": value, "domain": ".example-site.tld",
                        "path": "/", "httpOnly": False, "secure": True,
                        # Playwright reports -1 for a session cookie, not a missing key.
                        "expires": float(expiry) if expiry is not None else -1})
        return out

    async def add_cookies(self, _cookies):
        pass


class _PlaywrightPage:
    def __init__(self, world: World):
        self.world = world
        self.waited = False
        self.url = world.url
        self.context = _PlaywrightContext(self)
        self.main_frame = object()

    async def title(self):
        return self.world.title

    async def content(self):
        return self.world.html

    async def query_selector(self, _sel):
        return None

    async def goto(self, *_a, **_k):
        pass

    async def wait_for_load_state(self, *_a, **_k):
        pass

    async def screenshot(self):
        return self.world.screenshot

    async def route(self, *_a, **_k):
        pass

    async def unroute(self, *_a, **_k):
        pass

    def on(self, *_a, **_k):
        pass

    def remove_listener(self, *_a, **_k):
        pass


class _StealthCtx:
    def __init__(self, world: World):
        self.page = _PlaywrightPage(world)
        self.context = self.page.context
        self.user_agent = world.user_agent
        self.lock = asyncio.Lock()


class StealthHarness:
    name = "stealth"

    def solve(self, world: World, **fields):
        ctx = _StealthCtx(world)
        req = V1RequestBase(dict({"url": world.url, "disableMedia": False}, **fields))
        # __new__ rather than __init__: the constructor starts the background
        # event loop thread, and nothing on this path touches it.
        engine = StealthEngine.__new__(StealthEngine)
        real_sleep = asyncio.sleep

        async def _slept(seconds, *a, **k):
            if seconds:
                ctx.page.waited = True
            return await real_sleep(0)

        async def run():
            with patch('asyncio.sleep', _slept):
                return await engine._navigate_and_solve(req, ctx, "GET", 60.0)

        return asyncio.run(run())


HARNESSES = (ChromeHarness(), StealthHarness())
