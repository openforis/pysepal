"""The configuration of the pytest run."""

import atexit
import json
import logging
import os
import time
import uuid
from itertools import product
from pathlib import Path, PurePosixPath
from typing import Optional
from urllib.request import urlretrieve

import ee
import geopandas as gpd
import matplotlib
import pandas as pd
import pytest
from shapely import geometry as sg

from pysepal.scripts import utils as su
from pysepal.scripts.gee_interface import GEEInterface
from tests._janitor import delete_recursive

su.init_ee()


@pytest.fixture(autouse=True, scope="session")
def _sepalui_logs_reach_caplog():
    """Keep a developer's ``logging_config.toml`` from blinding ``caplog``.

    ``pysepal.logger`` applies that file at import if it sits beside the
    package, and a config that sets ``propagate = false`` on ``sepalui`` stops
    records reaching the root handler ``caplog`` installs. Every test that
    asserts on a log record then fails on that machine alone.
    """
    log = logging.getLogger("sepalui")
    previous = log.propagate
    log.propagate = True
    yield
    log.propagate = previous


_TERMINAL_FAILURES = ("FAILED", "CANCELLED", "CANCEL_REQUESTED")


def _wait_for_task(task: ee.batch.Task, timeout: float = 900) -> None:
    """Block until an export task completes, and raise if it does not.

    Replaces ``pysepal.scripts.gee.wait_for_completion``, removed in 4.0. That
    one looked the task up by description in the global account's task list and
    exited the loop on ``COMPLETED`` alone, so a cancelled task span forever.
    This holds the handle the export already returned.

    Args:
        task: a started ``ee.batch.Task``.
        timeout: seconds to wait before giving up.
    """
    deadline = time.monotonic() + timeout
    while True:
        state = task.status()["state"]
        if state == "COMPLETED":
            return
        if state in _TERMINAL_FAILURES:
            raise RuntimeError(f"export task {task.id} ended as {state}")
        if time.monotonic() > deadline:
            raise TimeoutError(f"export task {task.id} still {state} after {timeout}s")
        time.sleep(5)


# -- SEPAL related parameters --------------------------------------------------


@pytest.fixture(scope="session")
def file_start() -> str:
    """The start of any link to the sepal platform.

    Args:
        the value of the sandbox path
    """
    return "https://sepal.io/api/sandbox/jupyter/files/"


# -- Access files from the project ---------------------------------------------

# init pyplot with the non interactive backend and use it in the rest of the tests
matplotlib.use("Agg")


@pytest.fixture(scope="session")
def root_dir() -> Path:
    """Path to the root dir of the library.

    Returns:
        the root path
    """
    return Path(__file__).parents[1].absolute()


@pytest.fixture(scope="session")
def readme(root_dir: Path) -> Path:
    """Return the readme file path.

    Returns:
        the path to the file
    """
    return root_dir / "README.rst"


# -- generate a test file system in GEE ----------------------------------------


@pytest.fixture(scope="session")
def _hash() -> str:
    """Create a hash for each test instance.

    Returns:
        the hash string
    """
    return uuid.uuid4().hex


@pytest.fixture(scope="session")
def gee_dir(_hash: str) -> Optional[Path]:
    """Create a test dir based on earthengine initialization.

    Populated with fake super small assets under a shared container:

    pysepal-tests/sepal-ui-<hash>/
    ├── subfolder/
    │   └── subfolder_feature_collection
    ├── feature_collection
    └── image

    Cleaned up on normal teardown (L1), on interpreter exit (L2 atexit),
    and via `nox -s clean_gee_assets` (L3 janitor).

    Returns:
        the path to the gee dir inside user folder
    """
    if not ee.data.is_initialized():
        pytest.skip("Earthengine is not connected")

    # Compute the container and session paths
    project_id = ee.data.getProjectConfig()["name"].split("/")[1]
    assets_root = PurePosixPath(f"projects/{project_id}/assets/")
    container = assets_root / "pysepal-tests"
    gee_dir = container / f"sepal-ui-{_hash}"

    # Best-effort idempotent container creation; same-millisecond parallel races
    # are rare at test-fixture scale and fail loudly rather than corrupting state.
    try:
        ee.data.getAsset(str(container))
    except ee.EEException:
        ee.data.createAsset({"type": "FOLDER"}, str(container))

    # Session folder — must be unique per session, so no idempotency needed
    ee.data.createAsset({"type": "FOLDER"}, str(gee_dir))

    # L2: atexit safety net for interrupted/crashed sessions
    def _atexit_cleanup() -> None:
        try:
            if ee.data.is_initialized():
                delete_recursive(str(gee_dir))
        except Exception:
            # atexit swallows raised exceptions anyway; silence explicitly
            pass

    atexit.register(_atexit_cleanup)

    # create a subfolder
    subfolder = gee_dir / "subfolder"
    ee.data.createAsset({"type": "FOLDER"}, str(subfolder))

    # create test material
    centers = [sg.Point(i, j) for i, j in product([-50, 50], repeat=2)]
    data = list(range(len(centers)))
    gdf = gpd.GeoDataFrame({"data": data, "geometry": centers}, crs=3857).to_crs(4326)
    ee_gdf = ee.FeatureCollection(gdf.__geo_interface__)

    image = ee.Image.random(42).multiply(4).byte()

    lon = ee.Image.pixelLonLat().select("longitude")
    lat = ee.Image.pixelLonLat().select("latitude")
    image = (
        ee.Image(1)
        .where(lon.gt(0).And(lat.gt(0)), 2)
        .where(lon.lte(0).And(lat.lte(0)), 3)
        .where(lon.gt(0).And(lat.lte(0)), 4)
    )
    ee_buffer = ee.Geometry.Point(0, 0).buffer(200).bounds()
    image = image.clipToBoundsAndScale(ee_buffer, scale=30)

    # exports — should take less than 2 minutes unless there are concurrent tasks
    fc = "feature_collection"
    fc_task = ee.batch.Export.table.toAsset(
        collection=ee_gdf, description=f"{fc}_{_hash}", assetId=str(gee_dir / fc)
    )
    fc_task.start()

    subfolder_fc = "subfolder_feature_collection"
    subfolder_fc_task = ee.batch.Export.table.toAsset(
        collection=ee_gdf,
        description=f"{subfolder_fc}_{_hash}",
        assetId=str(subfolder / subfolder_fc),
    )
    subfolder_fc_task.start()

    rand_image = "image"
    image_task = ee.batch.Export.image.toAsset(
        image=image,
        description=f"{rand_image}_{_hash}",
        assetId=str(gee_dir / rand_image),
        region=ee_buffer,
    )
    image_task.start()

    # wait for completion of the exportation tasks before leaving this method
    for task in (fc_task, subfolder_fc_task, image_task):
        _wait_for_task(task)

    yield gee_dir

    # L1: primary teardown on normal session exit
    delete_recursive(str(gee_dir))


@pytest.fixture(scope="session")
def fake_asset(gee_dir: Path) -> Path:
    """Return the path to a fake asset.

    Returns:
        the path to the dir
    """
    return gee_dir / "feature_collection"


@pytest.fixture(scope="session")
def gee_user_dir(gee_dir: Path) -> Path:
    """Return the path to the gee_dir assets.

    Args:
        gee_dir: the path to the session defined GEE directory

    Returns:
        the path to gee_dir
    """
    return gee_dir


@pytest.fixture(scope="session")
def image_id() -> str:
    """The image id of an asset.

    Returns:
        the AssetId of Daniel Wiell asset
    """
    # testing asset from Daniel Wiell
    # may not live forever
    return "users/wiell/forum/visualization_example"


# -- create local tmp files ----------------------------------------------------


#: vendored GADM level-0 definition of Vatican City. Sourced once from
#: https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_VAT_0.json and committed so the
#: AOI test suite never has to reach the (slow/often-unreachable) GADM server. It backs
#: both the ``fake_vector`` fixture and the ``_offline_gadm`` pygadm interceptor below.
GADM_VAT_0 = Path(__file__).parent / "data" / "gadm41_VAT_0.geojson"


@pytest.fixture(autouse=True)
def _offline_gadm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Serve the vendored Vatican geometry instead of hitting the GADM server.

    ``pygadm.Items`` performs a single HTTP GET against geodata.ucdavis.edu to fetch the
    ``gadm41_<ISO>_<level>.json`` boundary. That host is frequently slow or unreachable
    from CI, which used to flake every AOI test that resolved an admin. We intercept that
    one call for the Vatican definition so the tests stay hermetic and fast; any other URL
    falls through to the real session.
    """
    import pygadm

    content = GADM_VAT_0.read_bytes()
    original_get = pygadm.session.get

    class _Response:
        def __init__(self, content: bytes) -> None:
            self.content = content

    def fake_get(url: str, *args, **kwargs):
        if "gadm41_VAT_0" in url:
            return _Response(content)
        return original_get(url, *args, **kwargs)

    monkeypatch.setattr(pygadm.session, "get", fake_get)


@pytest.fixture(scope="session")
def fake_vector(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a fake vector file from the GADM definition of vatican city and save it in the tmp dir.

    Returns:
        the path to the tmp vector file
    """
    file = tmp_path_factory.mktemp("temp") / "gadm41_VAT_0.shp"
    gpd.read_file(GADM_VAT_0).to_file(file)
    return file


@pytest.fixture(scope="session")
def fake_points(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a fake point file the tmp file.

    Returns:
        the path to the point file
    """
    tmp_file = tmp_path_factory.mktemp("temp") / "fake_point.csv"
    tmp_file.write_text("lat,lon,id\n1,1,0\n0,0,1")
    return tmp_file


@pytest.fixture(scope="session")
def fake_table(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a fake table.

    Returns:
        the path to the created file
    """
    tmp_file = tmp_path_factory.mktemp("temp") / "fake_table.csv"
    coloseo = [1, 41.89042582290999, 12.492241627092199]
    fao = [2, 41.88369224629387, 12.489216069409004]
    columns = ["id", "lat", "lng"]
    df = pd.DataFrame([coloseo, fao], columns=columns)
    df.to_csv(tmp_file, index=False)
    return tmp_file


@pytest.fixture(scope="session")
def wrong_table(fake_table: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a wrongly defined table (with 2 columns instead of the minimal 3.

    Args:
        fake_table: the path to the complete table

    Returns:
        the Path to the created file
    """
    tmp_file = tmp_path_factory.mktemp("temp") / "wrong_table.csv"
    df = pd.read_csv(fake_table).drop(["lng"], axis=1)
    df.to_csv(tmp_file, index=False)

    return tmp_file


@pytest.fixture(scope="session")
def rgb(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Add a raster file of the bahamas coming from rasterio test suit.

    Returns:
        the path to the image
    """
    file = tmp_path_factory.mktemp("temp") / "rgb.tif"
    link = "https://raw.githubusercontent.com/rasterio/rasterio/master/tests/data/RGB.byte.tif"
    urlretrieve(link, file)
    return file


@pytest.fixture(scope="session")
def byte(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Add a raster file of the bahamas coming from rasterio test suit.

    Returns:
        the path to the byte file
    """
    file = tmp_path_factory.mktemp("temp") / "byte.tif"
    link = "https://raw.githubusercontent.com/rasterio/rasterio/master/tests/data/byte.tif"
    urlretrieve(link, file)

    return file


@pytest.fixture(scope="session")
def int16_classes(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A two-class int16 raster, the shape most land cover products come in.

    Returns:
        the path to a raster of class 1 (left half) and class 2 (right half)
    """
    import numpy as np
    import rasterio as rio
    from rasterio.transform import from_origin

    file = tmp_path_factory.mktemp("temp") / "classes.tif"
    data = np.ones((64, 64), dtype="int16")
    data[:, 32:] = 2
    with rio.open(
        file,
        "w",
        driver="GTiff",
        height=64,
        width=64,
        count=1,
        dtype="int16",
        crs="EPSG:4326",
        transform=from_origin(0, 0, 0.01, 0.01),
    ) as ds:
        ds.write(data, 1)

    return file


@pytest.fixture(scope="session")
def _tile_cache_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Where prepared rasters are cached for the duration of the run."""
    return tmp_path_factory.mktemp("tile-cache")


@pytest.fixture(autouse=True)
def _tile_cache(_tile_cache_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep prepared rasters out of the developer's real ``~/.cache``.

    The raster fixtures land on a new tmp path every session, so a shared cache
    would gain an entry per run and never drop one.
    """
    monkeypatch.setenv("PYSEPAL_TILE_CACHE", str(_tile_cache_dir))


# -- Planet credentials --------------------------------------------------------


@pytest.fixture(scope="session")
def planet_key() -> str:
    """Get the planet key stored in env.

    Returns:
        the str key
    """
    return os.getenv("PLANET_API_KEY")


@pytest.fixture(scope="session")
def cred() -> list:
    """Get the credentials stored in env.

    Returns:
        credential as a list: [cred(username, password)]
    """
    credentials = json.loads(os.getenv("PLANET_API_CREDENTIALS"))

    return list(credentials.values())


@pytest.fixture(scope="session")
def has_active_planet_subscription(planet_key: str) -> bool:
    """Check if the current credentials have active Planet subscriptions.

    Returns:
        True if there are active subscriptions, False otherwise
    """
    if not planet_key:
        return False

    try:
        from pysepal.planetapi import PlanetModel

        model = PlanetModel(planet_key)
        # Try to get subscriptions - if it fails or returns empty, no active subs
        subs = model.get_subscriptions()
        return len(subs) > 0
    except Exception:
        return False


@pytest.fixture(scope="session")
def repo_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a dummy repo directory.

    Returns:
        Path to the repo dir
    """
    return tmp_path_factory.mktemp("repo_dir")


@pytest.fixture(scope="session")
def gee_interface() -> GEEInterface:
    """Create a GeeInterface instance for testing.

    Returns:
        An instance of GeeInterface
    """
    return GEEInterface()


@pytest.fixture(scope="session")
def has_sepal_credentials() -> bool:
    """Check if SEPAL credentials are available.

    Returns:
        True if all SEPAL credentials are set, False otherwise
    """
    sepal_user = os.getenv("SEPAL_USER")
    sepal_password = os.getenv("SEPAL_PASSWORD")
    sepal_host = os.getenv("SEPAL_HOST")
    return all([sepal_user, sepal_password, sepal_host])


@pytest.fixture(scope="session")
def gee_interface_with_sepal() -> Optional[GEEInterface]:
    """Create a GEEInterface instance with SEPAL headers for testing.

    Returns:
        An instance of GEEInterface with SEPAL session, or None if credentials are not available
    """
    sepal_user = os.getenv("SEPAL_USER")
    sepal_password = os.getenv("SEPAL_PASSWORD")
    sepal_host = os.getenv("SEPAL_HOST")

    if not all([sepal_user, sepal_password, sepal_host]):
        return None

    try:
        from eeclient.client import EESession
        from eeclient.helpers import get_sepal_headers_from_auth

        sepal_headers = get_sepal_headers_from_auth(sepal_user, sepal_password, sepal_host)
        session = EESession.from_sepal_headers(sepal_headers)
        return GEEInterface(session=session)
    except Exception as e:
        import traceback

        print(f"\n[ERROR] Failed to create GEEInterface with SEPAL: {e}")
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        return None
