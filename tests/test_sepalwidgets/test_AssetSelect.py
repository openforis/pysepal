"""Test the AssetSelect widget."""

import time
from pathlib import Path
from typing import Callable, List

import ee
import pytest

from pysepal import sepalwidgets as sw
from pysepal.message import msg


def wait_for_async(asset_select: sw.AssetSelect, action: Callable, timeout: float = 10) -> None:
    """Wait for an async action on AssetSelect to complete.

    Args:
        asset_select: the AssetSelect widget
        action: a callable that performs the async action (e.g., lambda: setattr(widget, 'v_model', value))
        timeout: maximum time to wait in seconds
    """
    # Perform the action
    action()

    # Wait for loading to finish
    start_time = time.time()
    while asset_select.loading:
        if time.time() - start_time > timeout:
            raise TimeoutError("AssetSelect async operation did not complete in time.")
        time.sleep(0.1)

    # Extra safety: wait for _loaded flag if items are being refreshed
    # This is needed for operations that trigger _get_items
    start_time = time.time()
    while not asset_select._loaded:
        if time.time() - start_time > timeout:
            raise TimeoutError("AssetSelect did not finish loading in time.")
        time.sleep(0.1)

    # Give extra time for trait synchronization to propagate
    time.sleep(0.2)


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_init(gee_dir: Path, gee_user_dir: Path, asset_select: sw.AssetSelect) -> None:
    """Init the widget.

    Args:
        gee_dir: the session defined GEE directory
        gee_user_dir: the gee_dir without the project information
    """
    # Test the fixture
    assert isinstance(asset_select, sw.AssetSelect)
    assert str(gee_user_dir / "image") in asset_select.items

    # create an asset select with an undefined type
    asset_select = sw.AssetSelect(folder=str(gee_dir), types=["toto"])

    # zero assets are represented by a disabled item
    no_asset_item = [
        {
            "text": msg("widgets.asset_select.no_assets", folder=str(gee_dir)),
            "disabled": True,
        }
    ]
    assert asset_select.items == no_asset_item

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_add_default(asset_select: sw.AssetSelect, default_items: List[str]) -> None:
    """Check that user can add default assets to the list.

    Args:
        asset_select: a fully defined asset widget
        default_items: a list of default assetId
    """
    # add a partial list of asset
    wait_for_async(asset_select, lambda: setattr(asset_select, "default_asset", default_items[1:]))
    assert (
        default_items[1] not in asset_select.items
    )  # because default_items[1] is FEATURE_COLLECTION

    # add the full list
    wait_for_async(asset_select, lambda: setattr(asset_select, "default_asset", default_items))
    assert default_items[0] in asset_select.items

    # add one item as a string
    wait_for_async(asset_select, lambda: setattr(asset_select, "default_asset", default_items[0]))
    assert default_items[0] in asset_select.items

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_validate(asset_select: sw.AssetSelect, default_items: List[str]) -> None:
    """Check asset that user cannot read cannot be selected.

    Args:
        asset_select: a fully defined asset widget
        default_items: a list of default assetId
    """
    # set a legit asset
    wait_for_async(asset_select, lambda: setattr(asset_select, "v_model", default_items[0]))
    assert asset_select.valid is True
    assert asset_select.error_messages is None
    assert asset_select.error is False

    # set a fake asset
    wait_for_async(asset_select, lambda: setattr(asset_select, "v_model", "toto/tutu"))
    assert asset_select.error_messages is not None
    assert asset_select.valid is False
    assert asset_select.error is True

    # set a real asset but with wrong type
    wait_for_async(asset_select, lambda: setattr(asset_select, "types", ["TABLE"]))
    wait_for_async(asset_select, lambda: setattr(asset_select, "v_model", default_items[0]))
    assert asset_select.error_messages is not None
    assert asset_select.valid is False
    assert asset_select.error is True

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_check_types(asset_select: sw.AssetSelect, gee_user_dir: Path) -> None:
    """Check only the specified types are displayed to the need user.

    Args:
        asset_select: a fully defined asset widget
        gee_user_dir: the path to the GEE directory
    """
    # check that the list of asset is complete
    assert str(gee_user_dir / "image") in asset_select.items
    assert str(gee_user_dir / "feature_collection") in asset_select.items
    assert str(gee_user_dir / "subfolder/subfolder_feature_collection") in asset_select.items

    # set an IMAGE type
    wait_for_async(asset_select, lambda: setattr(asset_select, "types", ["IMAGE"]))
    assert str(gee_user_dir / "image") in asset_select.items
    assert str(gee_user_dir / "feature_collection") not in asset_select.items
    assert str(gee_user_dir / "subfolder/subfolder_feature_collection") not in asset_select.items

    # set a type list with a non legit asset type
    wait_for_async(asset_select, lambda: setattr(asset_select, "types", ["IMAGE", "toto"]))
    assert asset_select.types == ["IMAGE"]

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_get_items(asset_select: sw.AssetSelect, gee_user_dir: Path) -> None:
    """Get items from a specific folder.

    Args:
        asset_select: a fully defined asset widget
        gee_user_dir: the path to the GEE directory
    """
    # test function itself
    asset_select.items = []
    wait_for_async(asset_select, lambda: asset_select._get_items())
    assert str(gee_user_dir / "image") in asset_select.items

    # Test button event
    # we should export an extra asset and check if the new one is here but
    # that is 30 extra seconds so we cannot afford yet
    asset_select.items = []
    wait_for_async(asset_select, lambda: asset_select.fire_event("click:prepend", None))
    assert str(gee_user_dir / "image") in asset_select.items


@pytest.fixture(scope="session")
def default_items() -> List[str]:
    """Some default public data from GEE.

    Returns:
        list of DEM, L1, SKYSAT images
    """
    return [
        "OSU/GIMP/DEM",
        "ASTER/AST_L1T_003",
        "SKYSAT/GEN-A/PUBLIC/ORTHO/RGB",
    ]


@pytest.fixture(scope="function")
def asset_select(gee_dir: Path) -> sw.AssetSelect:
    """Create an AssetSelect widget that waits for the asset list to load."""
    # This is done because the asset list is loaded asynchronously
    asset_select = sw.AssetSelect(folder=str(gee_dir))
    # 30s allows for cold-start of a fresh GEEInterface (new event loop +
    # thread + EE listAssets round-trip) on every function-scoped fixture
    # instantiation. The in-test wait_for_async helper above uses 10s.
    timeout = 30
    start_time = time.time()
    while not getattr(asset_select, "_loaded", False):
        if time.time() - start_time > timeout:
            raise TimeoutError("AssetSelect did not finish loading in time.")
        time.sleep(0.1)

    return asset_select
