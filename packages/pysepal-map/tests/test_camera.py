"""Test the insets, the fit options and the read-only contract traits."""

import importlib.metadata

import ipywidgets
import pysepal_map
import pytest
import traitlets
from pysepal_map import Controls, MapWidget


def record_open_state(monkeypatch):
    """Record the state each MapWidget's comm opens with."""
    opened = []
    open_comm = ipywidgets.Widget.open

    def recording_open(self):
        if isinstance(self, MapWidget):
            opened.append(self.get_state())
        open_comm(self)

    monkeypatch.setattr(ipywidgets.Widget, "open", recording_open)
    return opened


@pytest.mark.parametrize("bad", [-1, 1.5, True, None])
def test_set_insets_rejects_non_pixel_values(bad):
    with pytest.raises(ValueError):
        MapWidget().set_insets(left=bad)


def test_insets_start_at_zero():
    assert MapWidget().insets == {"left": 0, "right": 0, "top": 0, "bottom": 0}


def test_set_insets_publishes_all_four_sides():
    w = MapWidget()
    w.set_insets(left=300, bottom=40)
    assert w.insets == {"left": 300, "right": 0, "top": 0, "bottom": 40}


def test_a_rejected_inset_changes_nothing():
    w = MapWidget()
    w.set_insets(left=300)
    with pytest.raises(ValueError):
        w.set_insets(left=10, top=-1)
    assert w.insets == {"left": 300, "right": 0, "top": 0, "bottom": 0}


def test_fit_bounds_request_carries_max_zoom_and_zoom_out():
    w = MapWidget()
    w.fit_bounds((10, 10, 20, 20), max_zoom=12, zoom_out=1)
    assert (w.view_request["max_zoom"], w.view_request["zoom_out"]) == (12, 1)


def test_fit_bounds_without_max_zoom_sends_null():
    w = MapWidget()
    w.fit_bounds((10, 10, 20, 20))
    assert w.view_request["max_zoom"] is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_zoom": 25},
        {"max_zoom": -1},
        {"max_zoom": True},
        {"zoom_out": -1},
        {"zoom_out": float("nan")},
        {"zoom_out": float("inf")},
    ],
)
def test_fit_bounds_rejects_bad_options(kwargs):
    w = MapWidget()
    with pytest.raises(ValueError):
        w.fit_bounds((10, 10, 20, 20), **kwargs)
    assert w.view_request["seq"] == 1


@pytest.mark.parametrize("name", ["state", "view", "view_request", "insets"])
def test_contract_traits_are_read_only(name):
    with pytest.raises(traitlets.TraitError):
        setattr(MapWidget(), name, {})


def test_comm_opens_with_the_first_request(monkeypatch):
    opened = record_open_state(monkeypatch)
    MapWidget(center=(1, 2), zoom=3)
    assert opened[0]["view_request"] == {"seq": 1, "center": [1.0, 2.0], "zoom": 3.0}


def test_has_payload():
    w = MapWidget()
    d = w.add_payload(b"{}")
    assert w.has_payload(d) and not w.has_payload("0" * 64)


def test_version_is_consistent():
    assert pysepal_map.__version__ == "0.3.0" == importlib.metadata.version("pysepal-map")


def test_controls_scale_in_json():
    assert Controls().to_json() == {
        "zoom": True,
        "fullscreen": True,
        "scale": True,
        "coordinates": False,
    }
