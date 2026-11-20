import dataclasses
import hashlib

import pytest

from pysepal_map import (
    GeoJSONSource,
    Layer,
    MapState,
    MapWidget,
    PMTilesSource,
    RasterSource,
    VectorPaint,
)


def geo(widget, data=b"{}", **kw):
    return Layer("v", GeoJSONSource(widget.add_payload(data)), **kw)


def instance(widget, layer_id="v"):
    return next(x for x in widget.state["layers"] if x["id"] == layer_id)["instance"]


def test_add_payload_returns_the_sha256():
    widget = MapWidget()
    digest = widget.add_payload(b"abc")
    assert digest == hashlib.sha256(b"abc").hexdigest()
    assert widget.add_payload(b"abc") == digest
    assert widget._payloads == {digest: b"abc"}


def test_draw_increments_revision():
    widget = MapWidget()
    widget.draw(MapState())
    assert widget.state["revision"] == 1
    widget.draw(MapState())
    assert widget.state["revision"] == 2


def test_draw_with_unknown_digest_raises_keyerror():
    widget = MapWidget()
    with pytest.raises(KeyError, match="deadbeef"):
        widget.draw(MapState(layers=(Layer("v", GeoJSONSource("deadbeef")),)))
    assert widget.state == {}


def test_draw_drops_unreferenced_payloads():
    widget = MapWidget()
    layer = geo(widget, b"keep")
    widget.add_payload(b"orphan")
    widget.draw(MapState(layers=(layer,)))
    assert list(widget._payloads) == [layer.source.digest]
    widget.draw(MapState())
    assert widget._payloads == {}


def test_invalid_draw_preserves_previous_snapshot_and_bytes():
    widget = MapWidget()
    layer = geo(widget, b"keep")
    widget.draw(MapState(layers=(layer,)))
    before = dict(widget.state)
    extra = widget.add_payload(b"new")
    with pytest.raises(ValueError):
        MapState(layers=(dataclasses.replace(layer, opacity=float("nan")),))
    with pytest.raises(KeyError):
        widget.draw(MapState(layers=(layer, Layer("w", GeoJSONSource("nope")))))
    with pytest.raises(TypeError):
        widget.draw({"layers": []})
    assert widget.state == before
    assert set(widget._payloads) == {layer.source.digest, extra}
    widget.draw(MapState(layers=(layer,)))
    assert widget.state["revision"] == 2
    assert instance(widget) == 1


def test_readd_with_default_token_allocates_new_instance():
    widget = MapWidget()
    layer = geo(widget)
    widget.draw(MapState(layers=(layer,)))
    assert instance(widget) == 1
    widget.draw(MapState())
    widget.add_payload(b"{}")
    widget.draw(MapState(layers=(layer,)))
    assert instance(widget) == 2


def test_paint_only_changes_preserve_the_instance():
    widget = MapWidget()
    layer = geo(widget)
    widget.draw(MapState(layers=(layer,)))
    changed = dataclasses.replace(
        layer, paint=VectorPaint(stroke="#f00"), opacity=0.5, visible=False
    )
    widget.draw(MapState(layers=(changed,)))
    assert instance(widget) == 1


@pytest.mark.parametrize("change", ["digest", "url", "attribution", "token"])
def test_source_attribution_and_token_changes_retire_the_instance(change):
    widget = MapWidget()
    if change == "digest":
        layer = geo(widget, b"1")
        new = None
    else:
        layer = Layer("v", PMTilesSource("https://x/a.pmtiles", "roads"))
        new = {
            "url": dataclasses.replace(
                layer, source=PMTilesSource("https://x/b.pmtiles", "roads")
            ),
            "attribution": dataclasses.replace(layer, attribution="x"),
            "token": dataclasses.replace(layer, token=1),
        }[change]
    widget.draw(MapState(layers=(layer,)))
    if change == "digest":
        new = geo(widget, b"2")
    widget.draw(MapState(layers=(new,)))
    assert instance(widget) == 2


def test_instances_follow_input_order_and_keep_across_reorder():
    widget = MapWidget()
    a = Layer("a", RasterSource(("t",)))
    b = Layer("b", RasterSource(("u",)))
    widget.draw(MapState(layers=(a, b)))
    widget.draw(MapState(layers=(b, a)))
    assert instance(widget, "a") == 1
    assert instance(widget, "b") == 2
