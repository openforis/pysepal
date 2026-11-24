"""A same-origin route to the kernel's tile server, for apps served by solara-server.

``localtileserver`` binds ``127.0.0.1`` and sends no CORS headers, and MapLibre
fetches its tiles, so the browser reads them only from the page's own origin. Under
solara-server that origin is this process: the route forwards the tiles of the
rasters pysepal prepared, and nothing else. localtileserver opens whatever path or
URL a request names in ``filename``, so the route answers only for tile paths, and
only for the server and file a grant names.

Each raster's URLs carry a random token, granted for that server and file by
:func:`allow` until the raster's tile client is released. Only the page that drew the
raster receives its URLs, so in a process several users share, a page cannot read
another user's rasters, whatever paths it guesses.
"""

import http.client
import re
import secrets
import sys
import threading
import urllib.error
import urllib.request
import weakref
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

__all__ = ["PATH", "allow", "client_prefix", "serving"]

#: Where the route listens, below solara's root path.
PATH = "/_pysepal/tiles"

_TILE = re.compile(r"api/tiles/[0-9]+/[0-9]+/[0-9]+\.(png|jpe?g|webp)")
_GRANTED = re.compile(re.escape(PATH) + r"/([A-Za-z0-9_-]+)/([0-9]+)/")
_FORWARDED_HEADERS = ("content-type", "cache-control", "etag", "last-modified")
# The upstream is on loopback: an HTTP proxy from the environment cannot reach it.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

_lock = threading.Lock()
#: token -> (port, filename)
_grants: dict[str, tuple[int, str]] = {}


def _solara_app() -> Optional[Any]:
    """Solara's Starlette app when solara-server runs this process, else None.

    Read from ``sys.modules`` rather than imported: Voila, Jupyter and pytest import
    solara's kernel machinery but never its server.
    """
    return getattr(sys.modules.get("solara.server.starlette"), "app", None)


def serving() -> bool:
    """Whether solara-server is serving this process."""
    return _solara_app() is not None


def client_prefix() -> Optional[str]:
    """Return a tile URL prefix that reaches this process's route, mounting it once.

    Returns:
        ``{root_path}/_pysepal/tiles/{token}/{port}``, with a new token and
        ``{port}`` left for localtileserver to fill, or None when solara-server is
        not serving this process. The route answers for it once :func:`allow` has
        granted a URL made from it.
    """
    app = _solara_app()
    if app is None:
        return None
    _mount(app)
    from solara.server import settings

    root = (settings.main.root_path or "").rstrip("/")
    return f"{root}{PATH}/{secrets.token_urlsafe(16)}/{{port}}"


def allow(url: str, owner: object) -> None:
    """Let the route forward the tiles ``url`` names, until ``owner`` is collected.

    Args:
        url: a tile URL made from a :func:`client_prefix`, with its ``filename``.
        owner: the tile client the URL came from.
    """
    parsed = urlparse(url)
    granted = _GRANTED.search(parsed.path)
    if granted is None:
        raise ValueError(f"not a URL of the tile route: {url}")
    token, port = granted.group(1), int(granted.group(2))
    [filename] = parse_qs(parsed.query)["filename"]
    with _lock:
        _grants[token] = (port, filename)
    weakref.finalize(owner, _revoke, token)


def _revoke(token: str) -> None:
    with _lock:
        _grants.pop(token, None)


def _mount(app: Any) -> None:
    from starlette.routing import Route

    path = f"{PATH}/{{token}}/{{port:int}}/{{path:path}}"
    with _lock:
        routes = app.router.routes
        # A reload of this module mounts a new handler; the old one reads dead grants.
        if any(getattr(r, "endpoint", None) is _forward for r in routes):
            return
        routes[:] = [r for r in routes if not getattr(r, "path", "").startswith(f"{PATH}/")]
        # first: solara's catch-all page route would answer otherwise
        routes.insert(0, Route(path, _forward, methods=["GET", "HEAD"]))


def _fetch(url: str) -> tuple[int, dict[str, str], bytes]:
    try:
        with _OPENER.open(url, timeout=60) as upstream:
            return upstream.status, dict(upstream.headers), upstream.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read()


async def _forward(request: Any) -> Any:
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import Response

    params = request.path_params
    port, path = params["port"], params["path"]
    with _lock:
        grant = _grants.get(params["token"])
    # Every filename the query holds: localtileserver reads one of them.
    filenames = request.query_params.getlist("filename")
    if not (grant and filenames and all((port, f) == grant for f in filenames)):
        return Response(status_code=404)
    if not _TILE.fullmatch(path):
        return Response(status_code=404)
    try:
        status, headers, body = await run_in_threadpool(
            _fetch, f"http://127.0.0.1:{port}/{path}?{request.url.query}"
        )
    except (OSError, http.client.HTTPException):
        return Response(status_code=502)
    lower = {k.lower(): v for k, v in headers.items()}
    kept = {k: lower[k] for k in _FORWARDED_HEADERS if k in lower}
    return Response(body, status_code=status, headers=kept)
