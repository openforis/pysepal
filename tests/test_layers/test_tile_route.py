"""The same-origin route pysepal mounts for local raster tiles under solara-server."""

import gc
import http.client
import math
import re
import sys
import types
from urllib.parse import parse_qs, urlencode, urlparse

import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Mount, Route
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
    first = tile_route.client_prefix()
    assert re.fullmatch(r"/app/_pysepal/tiles/[A-Za-z0-9_-]{22}/\{port\}", first)
    assert tile_route.client_prefix() != first, "each prefix has its own token"
    routes = solara_server.router.routes
    mounted = [r for r in routes if r.path.startswith(tile_route.PATH)]
    assert len(mounted) == 1 and routes[0] is mounted[0]


@pytest.fixture
def bridged(monkeypatch) -> list:
    """The tile clients that turned jupyter-loopback's comm bridge on."""
    from localtileserver import TileClient

    calls: list = []
    monkeypatch.setattr(TileClient, "enable_jupyter_loopback", lambda self: calls.append(self))
    return calls


def _middle_tile(render) -> str:
    west, south, east, north = render.bounds
    return _tile(render.url, (west + east) / 2, (south + north) / 2, 12)


def test_a_local_raster_reaches_the_page_through_the_route(solara_server, byte, bridged):
    render = prepare_sync(LayerSpec.from_raster(byte, name="b"), optimize=False)
    port = render.keepalive.server_port
    token = re.fullmatch(
        r"/_pysepal/tiles/([^/]+)/(\d+)/api/tiles/\{z\}/.*", render.url.split("?")[0]
    )
    assert token and token.group(2) == str(port)
    assert bridged == []

    tile = _middle_tile(render)
    client = TestClient(solara_server)
    response = client.get(tile)
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"

    # only the tiles of the file and server the token was granted for
    assert client.get(_with_query(tile, filename="/etc/hostname")).status_code == 404
    assert client.get(tile.replace("/api/tiles/", "/api/metadata/")).status_code == 404
    assert client.get(tile.replace(f"/{port}/", f"/{port + 1}/")).status_code == 404
    assert client.get(tile.replace(token.group(1), "A" * 22)).status_code == 404
    twice = f"{tile}&filename=%2Fetc%2Fhostname"
    assert client.get(twice).status_code == 404, "localtileserver would read one of them"
    assert client.get("/raster-app").text == "page"


def test_a_composed_app_lists_the_route_itself(solara_server, byte):
    # The guide's composition: the Mount copies solara's routes before pysepal adds its own.
    composed = Starlette(
        routes=[tile_route.route(), Mount("/", routes=solara_server.router.routes)]
    )
    render = prepare_sync(LayerSpec.from_raster(byte, name="b"), optimize=False)
    response = TestClient(composed).get(_middle_tile(render))
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"


def test_a_raster_is_readable_only_with_its_own_token(solara_server, byte, tmp_path):
    """In a process several users share, knowing a path is not enough."""
    other = tmp_path / "other.tif"
    other.write_bytes(byte.read_bytes())
    mine = prepare_sync(LayerSpec.from_raster(byte, name="mine"), optimize=False)
    theirs = prepare_sync(LayerSpec.from_raster(other, name="theirs"), optimize=False)
    [their_file] = parse_qs(urlparse(theirs.url).query)["filename"]
    client = TestClient(solara_server)
    assert client.get(_with_query(_middle_tile(mine), filename=their_file)).status_code == 404
    assert client.get(_middle_tile(theirs)).status_code == 200


def test_the_grant_ends_with_the_tile_client(solara_server, byte):
    render = prepare_sync(LayerSpec.from_raster(byte, name="b"), optimize=False)
    tile = _middle_tile(render)
    client = TestClient(solara_server)
    assert client.get(tile).status_code == 200
    del render
    gc.collect()
    assert client.get(tile).status_code == 404


def test_the_route_refuses_odd_tile_paths_and_reports_upstream_failures(
    solara_server, byte, monkeypatch
):
    render = prepare_sync(LayerSpec.from_raster(byte, name="b"), optimize=False)
    tile = _middle_tile(render)
    client = TestClient(solara_server)
    # an Arabic-Indic digit is a digit to \d, not to localtileserver
    odd = re.sub(r"/api/tiles/\d+/", "/api/tiles/%D9%A1/", tile)
    assert client.get(odd).status_code == 404

    def disconnected(url):
        raise http.client.RemoteDisconnected("gone")

    monkeypatch.setattr(tile_route, "_fetch", disconnected)
    assert client.get(tile).status_code == 502


def test_the_route_ignores_the_environment_proxy(solara_server, byte, monkeypatch):
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    render = prepare_sync(LayerSpec.from_raster(byte, name="b"), optimize=False)
    assert TestClient(solara_server).get(_middle_tile(render)).status_code == 200


def test_a_set_prefix_wins_over_the_route(solara_server, byte, monkeypatch, bridged):
    monkeypatch.setenv(CLIENT_PREFIX_ENV_VAR, "/api/sandbox/jupyter/proxy/{port}")
    render = prepare_sync(LayerSpec.from_raster(byte, name="b"), optimize=False)
    assert render.url.startswith("/api/sandbox/jupyter/proxy/")
    # the bridge reaches no page under solara-server: the prefix's route serves the tiles
    assert bridged == []
