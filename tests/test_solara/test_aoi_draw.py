"""Tests for process_draw."""

import pytest

from pysepal.solara.components.aoi.draw import process_draw


def _single_polygon_feature(properties: dict) -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": properties,
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
                },
            }
        ],
    }


@pytest.mark.parametrize(
    "geo_json",
    [{}, {"type": "FeatureCollection", "features": []}],
)
def test_process_draw_rejects_empty_input(geo_json):
    with pytest.raises(ValueError):
        process_draw(geo_json, gee=False)


def test_process_draw_strips_style_property():
    geo = _single_polygon_feature({"name": "keep", "style": {"color": "red"}})

    result = process_draw(geo, name="plot", gee=False)

    assert "style" not in result.gdf.iloc[0]
    assert result.gdf.iloc[0]["name"] == "keep"


def test_process_draw_strips_only_what_the_drawing_tools_add():
    tools = {"mode": "circle", "radiusKilometers": 1.5, "style": {"color": "red"}}
    geo = _single_polygon_feature({**tools, "selected": "yes", "name": "keep"})

    result = process_draw(geo, name="plot", gee=False)

    assert list(result.gdf.columns) == ["geometry", "selected", "name"]
    assert result.spec.geo_json["features"][0]["properties"] == {"selected": "yes", "name": "keep"}


def test_process_draw_generates_timestamped_name_when_empty():
    geo = _single_polygon_feature({})

    result = process_draw(geo, name="", gee=False)

    assert result.name.startswith("drawn_")


def test_process_draw_returns_aoi_result_with_gdf():
    geo = _single_polygon_feature({"plot_id": "A"})

    result = process_draw(geo, name="area", gee=False)

    assert result.method == "DRAW"
    assert result.gee is False
    assert result.feature_collection is None
    assert result.admin is None
    assert len(result.gdf) == 1
    assert result.gdf.crs.to_epsg() == 4326
