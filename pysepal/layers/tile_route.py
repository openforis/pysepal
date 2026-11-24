"""A same-origin route to the kernel's tile server, for apps served by solara-server.

``localtileserver`` binds ``127.0.0.1`` and sends no CORS headers, and MapLibre
fetches its tiles, so the browser reads them only from the page's own origin. Under
solara-server that origin is this process: the route forwards the tiles of the
rasters pysepal prepared, and nothing else. localtileserver opens whatever path or
URL a request names in ``filename``, so the route answers only for tile paths and the
files :func:`allow` registered.
"""

import re
import sys
import threading
import urllib.error
import urllib.request
from typing import Any, Optional

__all__ = ["PATH", "allow", "client_prefix"]

#: Where the route listens, below solara's root path.
PATH = "/_pysepal/tiles"

_TILE = re.compile(r"api/tiles/\d+/\d+/\d+\.(png|jpe?g|webp)")
_FORWARDED_HEADERS = ("content-type", "cache-control", "etag", "last-modified")

_lock = threading.Lock()
_allowed: dict[int, set[str]] = {}


def _solara_app() -> Optional[Any]:
    """Solara's Starlette app when solara-server runs this process, else None.

    Read from ``sys.modules`` rather than imported: Voila, Jupyter and pytest import
    solara's kernel machinery but never its server.
    """
    return getattr(sys.modules.get("solara.server.starlette"), "app", None)


def client_prefix() -> Optional[str]:
    """Return the tile URL prefix that reaches this process's route, mounting it once.

    Returns:
        ``{root_path}/_pysepal/tiles/{port}``, with ``{port}`` left for
        localtileserver to fill, or None when solara-server is not serving this
        process.
    """
    app = _solara_app()
    if app is None:
        return None
    _mount(app)
    from solara.server import settings

    root = (settings.main.root_path or "").rstrip("/")
    return f"{root}{PATH}/{{port}}"


def allow(port: int, filename: str) -> None:
    """Let the route forward the tiles of ``filename`` from the server on ``port``."""
    with _lock:
        _allowed.setdefault(int(port), set()).add(filename)


def _mount(app: Any) -> None:
    from starlette.routing import Route

    path = f"{PATH}/{{port:int}}/{{path:path}}"
    with _lock:
        routes = app.router.routes
        # A reload of this module mounts a new handler; the old one reads a dead allowlist.
        if any(getattr(r, "endpoint", None) is _forward for r in routes):
            return
        routes[:] = [r for r in routes if getattr(r, "path", None) != path]
        # first: solara's catch-all page route would answer otherwise
        routes.insert(0, Route(path, _forward, methods=["GET", "HEAD"]))


def _fetch(url: str) -> tuple[int, dict[str, str], bytes]:
    try:
        with urllib.request.urlopen(url, timeout=60) as upstream:
            return upstream.status, dict(upstream.headers), upstream.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read()


async def _forward(request: Any) -> Any:
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import Response

    port, path = request.path_params["port"], request.path_params["path"]
    with _lock:
        allowed = request.query_params.get("filename") in _allowed.get(port, ())
    if not (allowed and _TILE.fullmatch(path)):
        return Response(status_code=404)
    try:
        status, headers, body = await run_in_threadpool(
            _fetch, f"http://127.0.0.1:{port}/{path}?{request.url.query}"
        )
    except OSError:
        return Response(status_code=502)
    lower = {k.lower(): v for k, v in headers.items()}
    kept = {k: lower[k] for k in _FORWARDED_HEADERS if k in lower}
    return Response(body, status_code=status, headers=kept)
