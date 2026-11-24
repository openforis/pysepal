"""Setup utilities for Solara applications using pysepal.

This module provides utilities to configure common Solara server settings
that are typically needed across all pysepal-based applications.
"""

import atexit
import hashlib
import importlib.resources
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Iterator, List, Optional, Tuple, Union

import solara
import solara.server.settings

from pysepal.frontend.styles import apply_palette
from pysepal.scripts.scratch import scratch_dir

from ._topology import is_serving_connections
from .asset_merger import merge_asset_files

logger = logging.getLogger("sepalui.solara.setup")

DEFAULT_FONT_AWESOME = "/@fortawesome/fontawesome-free@6.7.2/css/all.min.css"
# A closed page closes its kernel at once through Solara's close beacon. The cull
# only runs for a dropped connection, so it waits for the page to reconnect.
DEFAULT_CULL_TIMEOUT = "5m"

# Shared stylesheet consumed by BOTH runtimes; merged into the Solara assets
# ahead of the Solara override sheet. The Voila runtime loads the same file via
# frontend.styles.get_custom_css().
SHARED_BASE_CSS = Path(__file__).parent.parent / "frontend" / "css" / "base.css"

#: The folder of the merged assets that serves the map's JS and CSS.
MAP_BUNDLE_FOLDER = "pysepal-map"

# Prefixed with `const bundle = {folder, js, css}`. The bundle exports only
# `render`: anywidget awaits an `initialize` under a 2 s model timeout, which a
# slow first download of the bundle would miss.
_MAP_LOADER = """\
const root = (globalThis.solara && globalThis.solara.rootPath) || "";
const url = (file) =>
  new URL(`${root}/static/assets/${bundle.folder}/${file}`, location.href).href;

function load() {
  const css = new Promise((resolve) => {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = url(bundle.css);
    link.onload = () => resolve();
    link.onerror = () => {
      console.warn(`pysepal: the map stylesheet did not load: ${link.href}`);
      resolve();
    };
    document.head.append(link);
  });
  return Promise.all([import(url(bundle.js)), css]).then(([module]) => module.default);
}

const key = Symbol.for(`pysepal-map.bundle:${bundle.js}`);
// a failed load must not stay cached, or one network blip fails every later map
const widget = () =>
  (globalThis[key] ??= load().catch((error) => {
    delete globalThis[key];
    throw error;
  }));

export default {
  async render(props) {
    const map = await widget();
    if (map.initialize) throw new Error("pysepal: the map loader does not run initialize");
    if (props.signal && props.signal.aborted) return;
    return map.render(props);
  },
};
"""


def setup_theme_colors():
    """Configure default sepalui theme colors for the application."""
    apply_palette(solara.lab.theme.themes)


_merged_root: Optional[Path] = None
_merged_locations: Tuple[Path, ...] = ()


def setup_solara_server(
    extra_asset_locations: Optional[List[Union[str, Path]]] = None,
) -> None:
    """Configure common Solara server settings for pysepal applications.

    This function sets up standard configurations that are commonly needed
    across pysepal-based Solara applications, avoiding the need to duplicate
    these settings in every application.

    Always includes:
    - FontAwesome 6.7.2
    - pysepal common assets (CSS, JS)
    - A kernel cull timeout of 5 minutes, so a page can reconnect after a dropped connection
    - The map's JS and CSS as static files, which a page loads once for all its maps

    Solara serves extra assets from one location, so the CSS and JS of pysepal
    and of every extra location are merged into one folder. That folder is
    created once per process and removed at exit. A repeated call is cheap: with
    no new location and no changed source file it does nothing, and with new
    locations it merges the union into the same folder. Several apps in one
    server, or a reload of the app module, therefore share one folder.

    Args:
        extra_asset_locations: Additional asset locations to serve beyond pysepal's common assets

    """
    global _merged_root, _merged_locations

    solara.server.settings.assets.fontawesome_path = DEFAULT_FONT_AWESOME
    solara.server.settings.kernel.cull_timeout = DEFAULT_CULL_TIMEOUT

    sepal_common_assets = Path(__file__).parent / "common" / "assets"
    if not sepal_common_assets.exists():
        logger.warning(f"sepal_ui common assets directory not found: {sepal_common_assets}")
        return

    requested = [Path(location).resolve() for location in (extra_asset_locations or [])]
    new = tuple(dict.fromkeys(p for p in requested if p not in _merged_locations))
    if _merged_root is not None and not new and _merged_is_current(sepal_common_assets):
        logger.debug(f"Solara assets already merged at: {_merged_root / 'assets'}")
        _serve_map_bundle(_merged_root / "assets")
        return

    logger.debug("Setting up Solara server configuration for sepal_ui application")
    if _merged_root is None:
        _merged_root = scratch_dir(prefix="sepal_ui_assets_")
        atexit.register(_remove_merged_assets)
        logger.debug(f"Created temporary assets directory: {_merged_root}")
    _merged_root.mkdir(parents=True, exist_ok=True)
    _merged_locations += new
    if _merged_locations:
        logger.debug(f"Extra asset locations: {[str(p) for p in _merged_locations]}")

    merge_asset_files(
        sepal_common_assets,
        list(_merged_locations),
        _merged_root,
        base_css_files=[SHARED_BASE_CSS],
    )
    merged_assets_dir = _merged_root / "assets"
    solara.server.settings.assets.extra_locations = [str(merged_assets_dir)]
    logger.debug(f"Asset location set to merged directory: {merged_assets_dir}")
    _serve_map_bundle(merged_assets_dir)

    logger.info("Solara server configuration completed successfully")


def _serve_map_bundle(merged_assets_dir: Path) -> None:
    """Serve the map's JS and CSS as files, and send each map only a loader.

    anywidget imports an inline ``_esm`` from a new blob URL for every widget, so
    every map would send and evaluate the whole 2 MB bundle. The loader imports it
    by URL instead, which the browser fetches and evaluates once per page and
    caches. The ``?v=`` hash keeps a cached copy from outliving a release.

    Solara only: Voila and Jupyter serve no such file. Hot reload
    (``ANYWIDGET_HMR=1``) keeps the inline bundle, which anywidget watches.
    """
    if os.getenv("ANYWIDGET_HMR") == "1" or not is_serving_connections():
        return
    from pysepal_map import MapWidget

    source = importlib.resources.files("pysepal_map").joinpath("static")
    target = merged_assets_dir / MAP_BUNDLE_FOLDER
    target.mkdir(parents=True, exist_ok=True)
    bundle = {"folder": MAP_BUNDLE_FOLDER}
    for key, name in (("js", "widget.js"), ("css", "widget.css")):
        content = source.joinpath(name).read_bytes()
        served = target / name
        if not served.is_file() or served.read_bytes() != content:
            served.write_bytes(content)
        digest = hashlib.md5(content, usedforsecurity=False).hexdigest()
        bundle[key] = f"{name}?v={digest[:12]}"
    MapWidget._esm = f"const bundle = {json.dumps(bundle)};\n{_MAP_LOADER}"
    MapWidget._css = ""


def _merged_is_current(sepal_common_assets: Path) -> bool:
    """Whether the merged files are at least as new as every source file."""
    merged_css = _merged_root / "assets" / "custom.css"
    if not merged_css.exists():
        return False
    merged_at = merged_css.stat().st_mtime_ns
    return all(
        source.stat().st_mtime_ns <= merged_at for source in _source_files(sepal_common_assets)
    )


def _source_files(sepal_common_assets: Path) -> Iterator[Path]:
    if SHARED_BASE_CSS.is_file():
        yield SHARED_BASE_CSS
    yield from (path for path in sepal_common_assets.iterdir() if path.is_file())
    for location in _merged_locations:
        for pattern in ("**/*.css", "**/*.js"):
            yield from (path for path in location.glob(pattern) if path.is_file())


def _remove_merged_assets() -> None:
    """Delete the merged assets folder and forget it. Registered with ``atexit``."""
    global _merged_root, _merged_locations
    if _merged_root is not None:
        shutil.rmtree(_merged_root, ignore_errors=True)
    _merged_root = None
    _merged_locations = ()
