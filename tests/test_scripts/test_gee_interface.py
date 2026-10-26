"""Test the GEEInterface class."""

from pathlib import Path
from typing import Optional

import ee
import pytest

from pysepal.scripts.gee_interface import GEEInterface


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_initialization(gee_interface: GEEInterface) -> None:
    """Test that GEEInterface can be initialized.

    Args:
        gee_interface: the GEEInterface fixture
    """
    assert gee_interface is not None
    assert isinstance(gee_interface, GEEInterface)
    # Since 4.0 there is no session-less interface: an omitted session is
    # resolved from the machine's credentials on first access.
    assert gee_interface.session is not None
    assert gee_interface._closed is False

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_get_info(gee_interface: GEEInterface) -> None:
    """Test get_info method with a simple EE object.

    Args:
        gee_interface: the GEEInterface fixture
    """
    # Create a simple EE object
    ee_number = ee.Number(42)

    # Get info using the interface
    result = gee_interface.get_info(ee_number)

    assert result == 42

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_get_info_batch(gee_interface: GEEInterface) -> None:
    """Test get_info_batch method with multiple EE objects.

    Args:
        gee_interface: the GEEInterface fixture
    """
    # Create multiple EE objects
    ee_objects = [
        ee.Number(1),
        ee.Number(2),
        ee.Number(3),
    ]

    # Get info for all objects
    results = gee_interface.get_info_batch(ee_objects)

    assert len(results) == 3
    assert results == [1, 2, 3]

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_get_asset(gee_interface: GEEInterface, fake_asset: Path) -> None:
    """Test get_asset method.

    Args:
        gee_interface: the GEEInterface fixture
        fake_asset: a fake asset path from fixtures
    """
    # Get an existing asset
    asset = gee_interface.get_asset(str(fake_asset))

    assert asset is not None
    assert asset["type"] == "TABLE"
    assert asset["name"] == str(fake_asset)

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_get_asset_not_exists(gee_interface: GEEInterface, gee_dir: Path) -> None:
    """Test get_asset method with non-existing asset.

    Args:
        gee_interface: the GEEInterface fixture
        gee_dir: the test GEE directory
    """
    fake_path = str(gee_dir / "non_existing_asset")

    # Test with not_exists_ok=False (should raise)
    with pytest.raises(Exception):
        gee_interface.get_asset(fake_path, not_exists_ok=False)

    # Test with not_exists_ok=True (should return None)
    result = gee_interface.get_asset(fake_path, not_exists_ok=True)
    assert result is None

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_get_assets(gee_interface: GEEInterface, gee_dir: Path) -> None:
    """Test get_assets method.

    Args:
        gee_interface: the GEEInterface fixture
        gee_dir: the test GEE directory
    """
    assets = gee_interface.get_assets(str(gee_dir))

    assert assets is not None
    assert len(assets) > 0

    # Check that expected assets are present
    asset_names = [asset["name"] for asset in assets]
    expected_assets = [
        str(gee_dir / "feature_collection"),
        str(gee_dir / "image"),
        str(gee_dir / "subfolder"),
    ]

    for expected_asset in expected_assets:
        assert expected_asset in asset_names

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_get_folder(gee_interface: GEEInterface) -> None:
    """Test get_folder method.

    Args:
        gee_interface: the GEEInterface fixture
    """
    folder = gee_interface.get_folder()

    assert folder is not None
    assert isinstance(folder, str)
    assert folder.startswith("projects/")
    assert folder.endswith("/assets/")

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_get_map_id(gee_interface: GEEInterface) -> None:
    """Test get_map_id method.

    Args:
        gee_interface: the GEEInterface fixture
    """
    # Create a simple image
    image = ee.Image(1)

    # Get map ID
    map_id = gee_interface.get_map_id(image)

    assert map_id is not None
    assert "tile_fetcher" in map_id or "mapid" in map_id

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_context_manager() -> None:
    """Test that GEEInterface works as a context manager."""
    with GEEInterface() as interface:
        assert interface is not None
        assert not interface._closed

        # Test basic operation
        result = interface.get_info(ee.Number(42))
        assert result == 42

    # After context exits, interface should be closed
    assert interface._closed

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_close(gee_interface: GEEInterface) -> None:
    """Test close method.

    Args:
        gee_interface: the GEEInterface fixture
    """
    # Create a new interface for this test
    interface = GEEInterface()
    assert not interface._closed
    assert interface._async_thread.is_alive()
    assert interface._async_loop.is_running()

    # Close it
    interface.close()
    assert interface._closed
    assert not interface._async_thread.is_alive()
    assert interface._async_loop.is_closed()

    # Calling close again should be safe
    interface.close()
    assert interface._closed

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_export_table_to_asset(gee_interface: GEEInterface, gee_dir: Path, _hash: str) -> None:
    """Test export_table_to_asset method.

    Args:
        gee_interface: the GEEInterface fixture
        gee_dir: the test GEE directory
        _hash: the hash for unique naming
    """
    # Create a simple feature collection
    point = ee.FeatureCollection(ee.Geometry.Point([1.5, 1.5]))
    asset_id = str(gee_dir / f"test_export_{_hash}")
    description = f"test_export_{_hash}"

    # Export to asset
    task = gee_interface.export_table_to_asset(
        collection=point, asset_id=asset_id, description=description
    )

    assert task is not None

    # Clean up - cancel the task if it's still running
    if hasattr(task, "cancel"):
        try:
            task.cancel()
        except Exception:
            pass

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_export_image_to_asset(gee_interface: GEEInterface, gee_dir: Path, _hash: str) -> None:
    """Test export_image_to_asset method.

    Args:
        gee_interface: the GEEInterface fixture
        gee_dir: the test GEE directory
        _hash: the hash for unique naming
    """
    # Create a simple image
    image = ee.Image(1)
    asset_id = str(gee_dir / f"test_image_export_{_hash}")
    description = f"test_image_export_{_hash}"

    # Export to asset
    task = gee_interface.export_image_to_asset(
        image=image,
        asset_id=asset_id,
        description=description,
        region=ee.Geometry.Point([0, 0]).buffer(1000),
        scale=1000,
    )

    assert task is not None

    # Clean up - cancel the task if it's still running
    if hasattr(task, "cancel"):
        try:
            task.cancel()
        except Exception:
            pass

    return


# -- Tests with SEPAL headers --------------------------------------------------


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_initialization_with_sepal(
    gee_interface_with_sepal: Optional[GEEInterface], has_sepal_credentials: bool
) -> None:
    """Test that GEEInterface can be initialized with SEPAL headers.

    Args:
        gee_interface_with_sepal: the GEEInterface fixture with SEPAL session
        has_sepal_credentials: whether SEPAL credentials are available
    """
    if not has_sepal_credentials or gee_interface_with_sepal is None:
        pytest.skip("SEPAL credentials not available")

    assert gee_interface_with_sepal is not None
    assert isinstance(gee_interface_with_sepal, GEEInterface)
    assert gee_interface_with_sepal.session is not None
    assert gee_interface_with_sepal._closed is False

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_get_info_with_sepal(
    gee_interface_with_sepal: Optional[GEEInterface], has_sepal_credentials: bool
) -> None:
    """Test get_info method with SEPAL headers.

    Args:
        gee_interface_with_sepal: the GEEInterface fixture with SEPAL session
        has_sepal_credentials: whether SEPAL credentials are available
    """
    if not has_sepal_credentials or gee_interface_with_sepal is None:
        pytest.skip("SEPAL credentials not available")

    # Create a simple EE object
    ee_number = ee.Number(42)

    # Get info using the interface with SEPAL headers
    result = gee_interface_with_sepal.get_info(ee_number)

    assert result == 42

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_get_asset_with_sepal(
    gee_interface_with_sepal: Optional[GEEInterface],
    fake_asset: Path,
    has_sepal_credentials: bool,
) -> None:
    """Test get_asset method with SEPAL headers.

    Args:
        gee_interface_with_sepal: the GEEInterface fixture with SEPAL session
        fake_asset: a fake asset path from fixtures
        has_sepal_credentials: whether SEPAL credentials are available
    """
    if not has_sepal_credentials or gee_interface_with_sepal is None:
        pytest.skip("SEPAL credentials not available")

    # Get an existing asset
    asset = gee_interface_with_sepal.get_asset(str(fake_asset))

    assert asset is not None
    assert asset["type"] == "TABLE"
    assert asset["name"] == str(fake_asset)

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_get_assets_with_sepal(
    gee_interface_with_sepal: Optional[GEEInterface],
    gee_dir: Path,
    has_sepal_credentials: bool,
) -> None:
    """Test get_assets method with SEPAL headers.

    Args:
        gee_interface_with_sepal: the GEEInterface fixture with SEPAL session
        gee_dir: the test GEE directory
        has_sepal_credentials: whether SEPAL credentials are available
    """
    if not has_sepal_credentials or gee_interface_with_sepal is None:
        pytest.skip("SEPAL credentials not available")

    assets = gee_interface_with_sepal.get_assets(str(gee_dir))

    assert assets is not None
    assert len(assets) > 0

    # Check that expected assets are present
    asset_names = [asset["name"] for asset in assets]
    expected_assets = [
        str(gee_dir / "feature_collection"),
        str(gee_dir / "image"),
        str(gee_dir / "subfolder"),
    ]

    for expected_asset in expected_assets:
        assert expected_asset in asset_names

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_get_folder_with_sepal(
    gee_interface_with_sepal: Optional[GEEInterface], has_sepal_credentials: bool
) -> None:
    """Test get_folder method with SEPAL headers.

    Args:
        gee_interface_with_sepal: the GEEInterface fixture with SEPAL session
        has_sepal_credentials: whether SEPAL credentials are available
    """
    if not has_sepal_credentials or gee_interface_with_sepal is None:
        pytest.skip("SEPAL credentials not available")

    folder = gee_interface_with_sepal.get_folder()

    assert folder is not None
    assert isinstance(folder, str)
    assert folder.startswith("projects/")
    assert folder.endswith("/assets/")

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_get_map_id_with_sepal(
    gee_interface_with_sepal: Optional[GEEInterface], has_sepal_credentials: bool
) -> None:
    """Test get_map_id method with SEPAL headers.

    Args:
        gee_interface_with_sepal: the GEEInterface fixture with SEPAL session
        has_sepal_credentials: whether SEPAL credentials are available
    """
    if not has_sepal_credentials or gee_interface_with_sepal is None:
        pytest.skip("SEPAL credentials not available")

    # Create a simple image
    image = ee.Image(1)

    # Get map ID
    map_id = gee_interface_with_sepal.get_map_id(image)

    assert map_id is not None
    assert "tile_fetcher" in map_id or "mapid" in map_id

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_get_bounds_geometry(gee_interface: GEEInterface) -> None:
    """get_bounds returns the extent of a plain ee.Geometry.

    Args:
        gee_interface: the GEEInterface fixture
    """
    bounds = gee_interface.get_bounds(ee.Geometry.BBox(1.0, 2.0, 3.0, 4.0))

    assert len(bounds) == 4
    assert list(bounds) == pytest.approx([1.0, 2.0, 3.0, 4.0], abs=1e-4)

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_get_bounds_dense_aoi(gee_interface: GEEInterface) -> None:
    """get_bounds returns the extent of a dense FeatureCollection.

    Regression for #996: GAUL 2024 Indonesia has over 2M edges. Its geometry
    bounds used to fail, but Earth Engine may now evaluate them successfully.
    Assert the supported result instead of depending on that server error.

    Args:
        gee_interface: the GEEInterface fixture
    """
    pygaul = pytest.importorskip("pygaul")
    indonesia = pygaul.Items(admin="241")  # GAUL 2024 Indonesia

    minx, miny, maxx, maxy = gee_interface.get_bounds(indonesia)

    assert minx == pytest.approx(95.0108, abs=0.05)
    assert miny == pytest.approx(-11.0076, abs=0.05)
    assert maxx == pytest.approx(141.0194, abs=0.05)
    assert maxy == pytest.approx(6.0769, abs=0.05)

    return
