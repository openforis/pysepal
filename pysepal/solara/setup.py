"""Setup utilities for Solara applications using pysepal.

This module provides utilities to configure common Solara server settings
that are typically needed across all pysepal-based applications.
"""

import atexit
import logging
import shutil
from pathlib import Path
from typing import Iterator, List, Optional, Tuple, Union

import solara
import solara.server.settings

from pysepal.scripts.scratch import scratch_dir

from .asset_merger import merge_asset_files

logger = logging.getLogger("sepalui.solara.setup")

DEFAULT_FONT_AWESOME = "/@fortawesome/fontawesome-free@6.7.2/css/all.min.css"
DEFAULT_CULL_TIMEOUT = "0s"

# Shared stylesheet consumed by BOTH runtimes; merged into the Solara assets
# ahead of the Solara override sheet. The Voila runtime loads the same file via
# frontend.styles.get_custom_css().
SHARED_BASE_CSS = Path(__file__).parent.parent / "frontend" / "css" / "base.css"


def setup_theme_colors():
    """Configure default sepalui theme colors for the application."""
    # Dark theme colors
    solara.lab.theme.themes.dark.primary = "#76591e"
    solara.lab.theme.themes.dark.primary_contrast = "#bf8f2d"
    solara.lab.theme.themes.dark.secondary = "#363e4f"
    solara.lab.theme.themes.dark.secondary_contrast = "#5d76ab"
    solara.lab.theme.themes.dark.error = "#a63228"
    solara.lab.theme.themes.dark.info = "#c5c6c9"
    solara.lab.theme.themes.dark.success = "#3f802a"
    solara.lab.theme.themes.dark.warning = "#b8721d"
    solara.lab.theme.themes.dark.accent = "#272727"
    solara.lab.theme.themes.dark.anchor = "#f3f3f3"
    solara.lab.theme.themes.dark.main = "#24221f"
    solara.lab.theme.themes.dark.darker = "#1a1a1a"
    solara.lab.theme.themes.dark.bg = "#121212"
    solara.lab.theme.themes.dark.menu = "#424242"

    # Light theme colors
    solara.lab.theme.themes.light.primary = "#5BB624"
    solara.lab.theme.themes.light.primary_contrast = "#76b353"
    solara.lab.theme.themes.light.accent = "#f3f3f3"
    solara.lab.theme.themes.light.anchor = "#f3f3f3"
    solara.lab.theme.themes.light.secondary = "#2199C4"
    solara.lab.theme.themes.light.secondary_contrast = "#5d76ab"
    solara.lab.theme.themes.light.main = "#2196f3"
    solara.lab.theme.themes.light.darker = "#ffffff"
    solara.lab.theme.themes.light.bg = "#FFFFFF"
    solara.lab.theme.themes.light.menu = "#FFFFFF"


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
    - No kernel timeout ("0s") (helps to kill sessions once the page is closed)

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

    logger.info("Solara server configuration completed successfully")


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
