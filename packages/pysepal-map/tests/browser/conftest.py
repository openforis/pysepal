"""Browser test fixtures: a Solara page with the pysepal-map probes."""

import os
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

import pytest

# The generic widget has no Vuetify to warm up.
os.environ.setdefault("SOLARA_TEST_VUETIFY_WARMUP", "false")

HARNESS = Path(__file__).parent / ".build" / "harness.js"


@pytest.fixture
def harness(solara_test, page_session):
    """The test page with the probes of harness.ts loaded as ``psmHarness``."""
    if not HARNESS.exists():
        pytest.fail(f"{HARNESS} is missing: run `npm run build:harness`")
    page_session.add_script_tag(path=HARNESS)
    return page_session


def png(rgb, size=256):
    """A one-colour PNG."""

    def chunk(kind, body):
        crc = zlib.crc32(kind + body)
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", crc)

    rows = b"".join(b"\x00" + bytes(rgb) * size for _ in range(size))
    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


GREEN_PNG = png((0, 160, 0))


@dataclass
class Tiles:
    """Raster tile sets on the page's own origin, answered by a Playwright route.

    Every tile is a green PNG, except in a set marked with ``fail_one``: the
    first tile it is asked for answers 500, and so does every retry of it.
    """

    PREFIX: ClassVar[str] = "/psm-test-tiles/"

    origin: str
    failing: set = field(default_factory=set)
    failed: dict = field(default_factory=dict)
    served: list = field(default_factory=list)

    def url(self, name):
        return f"{self.origin}{self.PREFIX}{name}/{{z}}/{{x}}/{{y}}.png"

    def fail_one(self, name):
        self.failing.add(name)

    def handle(self, route):
        url = route.request.url
        name = url.split(self.PREFIX, 1)[1].split("/", 1)[0]
        if name in self.failing and self.failed.setdefault(name, url) == url:
            route.fulfill(status=500, body="deliberate failure")
        else:
            self.served.append(url)
            route.fulfill(status=200, content_type="image/png", body=GREEN_PNG)


@pytest.fixture
def tiles(harness, page_session):
    """Local raster tiles for the test page; see ``Tiles``."""
    server = Tiles(page_session.evaluate("location.origin"))
    pattern = f"{server.origin}{Tiles.PREFIX}**"
    page_session.route(pattern, server.handle)
    yield server
    page_session.unroute(pattern, server.handle)
