"""The same-origin route pysepal mounts for local raster tiles under solara-server."""

import math
import sys
import types
from urllib.parse import parse_qs, urlencode, urlparse

import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from pysepal.layers import LayerSpec, prepare_sync, tile_route
from pysepal.layers.preparation import CLIENT_PREFIX_ENV_VAR


@pytest.fixture
def solara_server(monkeypatch):
    """Stage solara-server: its module in ``sys.modules``, with a catch-all page route."""
    from solara.server import settings

    app = Starlette(routes=[Route("/{fullpath:path}", lambda request: PlainTextResponse("page"))])
    module = types.ModuleType("solara.server.starlette")
    module.app = app
    monkeypatch.setitem(sys.modules, "solara.server.starlette", module)
    monkeypatch.setattr(settings.main, "root_path", "")
    monkeypatch.delenv(CLIENT_PREFIX_ENV_VAR, raising=False)
    return app


def _tile(template: str, lon: float, lat: float, zoom: int) -> str:
    n = 2**zoom
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return template.replace("{z}", str(zoom)).replace("{x}", str(x)).replace("{y}", str(y))


def _with_query(url: str, **changes: str) -> str:
    parsed = urlparse(url)
    query = {k: v[0] for k, v in parse_qs(parsed.query).items()} | changes
    return parsed._replace(query=urlencode(query)).geturl()


def test_no_prefix_without_solara_server(monkeypatch):
    monkeypatch.delitem(sys.modules, "solara.server.starlette", raising=False)
    assert tile_route.client_prefix() is None


def test_the_route_mounts_once_below_solara_root_path(solara_server, monkeypatch):
    from solara.server import settings

    monkeypatch.setattr(settings.main, "root_path", "/app/")
    assert tile_route.client_prefix() == "/app/_pysepal/tiles/{port}"
    tile_route.client_prefix()
    routes = solara_server.router.routes
    mounted = [r for r in routes if r.path.startswith(tile_route.PATH)]
    assert len(mounted) == 1 and routes[0] is mounted[0]


def test_a_local_raster_reaches_the_page_through_the_route(solara_server, byte, monkeypatch):
    from localtileserver import TileClient

    bridged = []
    monkeypatch.setattr(TileClient, "enable_jupyter_loopback", lambda self: bridged.append(self))
    render = prepare_sync(LayerSpec.from_raster(byte, name="b"), optimize=False)
    port = render.keepalive.server_port
    assert render.url.startswith(f"/_pysepal/tiles/{port}/api/tiles/{{z}}/")
    assert bridged == []

    west, south, east, north = render.bounds
    tile = _tile(render.url, (west + east) / 2, (south + north) / 2, 12)
    client = TestClient(solara_server)
    response = client.get(tile)
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"

    # only the tiles of the files pysepal prepared, from the servers it started
    assert client.get(_with_query(tile, filename="/etc/hostname")).status_code == 404
    assert client.get(tile.replace("/api/tiles/", "/api/metadata/")).status_code == 404
    assert client.get(tile.replace(f"/{port}/", f"/{port + 1}/")).status_code == 404
    assert client.get("/raster-app").text == "page"


def test_a_set_prefix_wins_over_the_route(solara_server, byte, monkeypatch):
    monkeypatch.setenv(CLIENT_PREFIX_ENV_VAR, "/api/sandbox/jupyter/proxy/{port}")
    render = prepare_sync(LayerSpec.from_raster(byte, name="b"), optimize=False)
    assert render.url.startswith("/api/sandbox/jupyter/proxy/")
