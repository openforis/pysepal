"""pysepal declares the in-repo map widget as a dependency."""

from importlib.metadata import requires, version

from packaging.version import Version


def test_pysepal_requires_a_widget_with_insets():
    assert "mapframe>=0.3.0" in [r.replace(" ", "") for r in requires("pysepal")]
    assert Version(version("mapframe")) >= Version("0.3.0")
