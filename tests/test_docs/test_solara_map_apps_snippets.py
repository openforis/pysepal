"""Every runnable snippet of ``docs/guides/solara-map-apps.md`` renders.

A Python block after a ``<!-- run -->`` line defines a ``Page`` component. Each one runs
on its own, with Solara's hook rules raising, and ``Page`` renders on a live loop, as
under a Solara server, with Earth Engine stubbed and no network. The layers it adds
must be drawn, nothing may log an error, and every map it builds must close with the
render context: the guide says the owner closes its maps. The pool-worker snippet's
button is also clicked, and what it adds must reach the map and the legend. A block after
``<!-- fragment -->`` is illustrative and does not run; an unmarked block fails.
"""

import asyncio
import linecache
import logging
import socket
from dataclasses import dataclass
from pathlib import Path

import ipyvuetify as v
import pytest
import solara
import solara.settings

import pysepal.scripts.utils as su
from pysepal.mapping import SepalMap
from pysepal.solara.components import map_view
from pysepal.solara.session_manager import SessionManager
from pysepal.solara.theme import _theme_store

GUIDE = Path(__file__).resolve().parents[2] / "docs" / "guides" / "solara-map-apps.md"
MARKS = ("<!-- run -->", "<!-- fragment -->")


@dataclass
class Snippet:
    line: int
    mark: str
    code: str


def _snippets(text: str) -> list[Snippet]:
    """The Python blocks of ``text``, each with the mark on the line before it, if any."""
    lines = text.splitlines()
    found, i = [], 0
    while i < len(lines):
        fence = lines[i].strip()
        if not fence.startswith("```"):
            i += 1
            continue
        start, indent = i, len(lines[i]) - len(lines[i].lstrip())
        i += 1
        while i < len(lines) and lines[i].strip() != "```":
            i += 1
        if fence == "```python":
            before = next((ln.strip() for ln in reversed(lines[:start]) if ln.strip()), "")
            body = "\n".join(ln[indent:] for ln in lines[start + 1 : i])
            found.append(Snippet(start + 1, before if before in MARKS else "", body))
        i += 1
    return found


SNIPPETS = _snippets(GUIDE.read_text(encoding="utf-8")) if GUIDE.is_file() else []
RUNNABLE = [s for s in SNIPPETS if s.mark == "<!-- run -->"]


class _FakeGee:
    """An Earth Engine interface that is never called: the snippets only render."""


def _no_network(*args, **kwargs):
    raise OSError("the guide's snippets must render without the network")


@pytest.fixture
def offline(monkeypatch):
    """Stub Earth Engine and the network, and collect every map built."""
    monkeypatch.setattr(SessionManager, "get_gee_interface", lambda self: _FakeGee())
    monkeypatch.setattr(su, "init_ee", lambda: None)
    monkeypatch.setattr(socket.socket, "connect", _no_network)
    monkeypatch.delenv("LOCALTILESERVER_CLIENT_PREFIX", raising=False)

    built = []
    init = SepalMap.__init__

    def recording_init(self, *args, **kwargs):
        built.append(self)
        init(self, *args, **kwargs)

    monkeypatch.setattr(SepalMap, "__init__", recording_init)
    SessionManager._instance = None
    _theme_store.clear()
    yield built
    SessionManager._instance = None
    _theme_store.clear()


def test_the_guide_has_runnable_snippets():
    assert GUIDE.is_file(), f"{GUIDE} is missing"
    assert RUNNABLE, "no snippet is marked <!-- run -->"


def test_every_python_block_is_marked():
    unmarked = [s.line for s in SNIPPETS if not s.mark]
    assert unmarked == [], f"mark these blocks <!-- run --> or <!-- fragment -->: lines {unmarked}"


def _undrawn(maps: list) -> list[str]:
    """The layers of ``maps`` that the engine has not drawn, or that failed."""
    return [
        layer_id
        for m in maps
        for layer_id in m.layer_store.ids
        if m.layer_engine.accepted(layer_id) is None
        or m.layer_store.view(layer_id).status == "error"
    ]


async def _settle(maps: list, timeout: float = 10.0) -> list[str]:
    """Keep the loop running until every layer is drawn, or ``timeout``; what is left."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while _undrawn(maps) and loop.time() < deadline:
        await asyncio.sleep(0.01)
    return _undrawn(maps)


def _load(snippet: Snippet, monkeypatch) -> dict:
    """Run a snippet's code, with Solara's hook rules raising; its namespace."""
    # the source, for Solara's hook check, which reads it when @solara.component runs
    filename = f"{GUIDE}:{snippet.line}"
    lines = snippet.code.splitlines(keepends=True)
    monkeypatch.setitem(linecache.cache, filename, (len(snippet.code), None, lines, filename))
    monkeypatch.setattr(solara.settings.main, "check_hooks", "raise")
    namespace = {"__name__": f"solara_map_apps_line{snippet.line}"}
    exec(compile(snippet.code, filename, "exec"), namespace)
    assert "Page" in namespace, "a runnable snippet defines Page"
    return namespace


@pytest.mark.parametrize("snippet", RUNNABLE, ids=[f"line{s.line}" for s in RUNNABLE])
def test_the_snippet_renders(snippet, offline, monkeypatch, caplog):
    caplog.set_level(logging.ERROR)
    namespace = _load(snippet, monkeypatch)

    async def render():
        root, rc = solara.render(namespace["Page"](), handle_error=False)
        try:
            assert rc.find(SepalMap).widgets, "the page shows its map"
            assert await _settle(offline) == [], "every layer the snippet adds is drawn"
        finally:
            rc.close()

    asyncio.run(render())
    assert offline, "the snippet builds a map"
    assert [m for m in offline if m.comm is not None] == [], "the owner closes every map"
    assert [r.getMessage() for r in caplog.records] == [], "nothing logs an error"


def test_the_pool_worker_snippet_draws_what_its_button_adds(offline, monkeypatch, caplog):
    """The spec built on a pool worker reaches the store on the loop, the map and the legend."""
    [snippet] = [s for s in RUNNABLE if "asyncio.to_thread(sample_sites" in s.code]
    caplog.set_level(logging.ERROR)
    namespace = _load(snippet, monkeypatch)

    async def run():
        root, rc = solara.render(namespace["Page"](), handle_error=False)
        try:
            [m] = offline
            [button] = rc.find(v.Btn).widgets
            button.fire_event("click", {})
            loop = asyncio.get_running_loop()
            deadline = loop.time() + 10
            while "sites" not in m.layer_store.ids and loop.time() < deadline:
                await asyncio.sleep(0.01)
            assert await _settle(offline) == [], "the sites are drawn"
            await m.layer_engine.wait_idle()  # the publish the legend reads
            assert m.layer_store.ids == ["sites"]
            listed = [entry["id"] for entry in map_view._legends(m)["all"]]
            assert listed == ["sites"], "the legend lists them"
        finally:
            rc.close()

    asyncio.run(run())
    assert [r.getMessage() for r in caplog.records] == [], "nothing logs an error"


def test_the_whole_app_adds_its_layer_once_an_area_is_picked(offline, monkeypatch, caplog):
    """The whole app's button waits for an area, then its task adds the Earth Engine layer."""
    from pysepal.solara.components.aoi.aoi_result import AoiResult
    from pysepal.solara.notifications import NotificationProvider

    [snippet] = [s for s in RUNNABLE if "def TreeCoverPanel" in s.code]
    caplog.set_level(logging.ERROR)
    namespace = _load(snippet, monkeypatch)

    class _Image:
        def select(self, *args):
            return self

        def clip(self, *args):
            return self

    added = []

    async def add_ee_layer_async(self, image, vis_params, name, key=""):
        added.append((name, key))

    monkeypatch.setattr(namespace["ee"], "Image", lambda *args: _Image())
    monkeypatch.setattr(SepalMap, "add_ee_layer_async", add_ee_layer_async)
    aoi = solara.reactive(None)

    @solara.component
    def Host():
        m = solara.use_memo(lambda: SepalMap(gee=False), [])
        NotificationProvider()
        namespace["TreeCoverPanel"](m, aoi)

    def button(rc):
        [found] = [b for b in rc.find(v.Btn).widgets if "Show tree cover" in str(b.children)]
        return found

    async def run():
        root, rc = solara.render(Host(), handle_error=False)
        try:
            assert button(rc).disabled, "no area yet"
            aoi.set(AoiResult(method="DRAW", name="area", feature_collection=object()))
            assert not button(rc).disabled
            button(rc).fire_event("click", {})
            loop = asyncio.get_running_loop()
            deadline = loop.time() + 10
            while not added and loop.time() < deadline:
                await asyncio.sleep(0.01)
            assert added == [("Tree cover", "tree_cover")]
        finally:
            rc.close()

    asyncio.run(run())
    assert [r.getMessage() for r in caplog.records] == [], "nothing logs an error"
