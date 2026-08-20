"""AoiSpec is the serializable record of what the user picked."""

import pytest

from pysepal.solara.components.aoi.aoi_spec import AOI_SPEC_SCHEMA_VERSION, AoiSpec


def test_admin_spec_round_trips_the_whole_cascade():
    spec = AoiSpec(method="ADMIN2", admin_codes=("101", "1001", "100001"))

    restored = AoiSpec.from_dict(spec.to_dict())

    assert restored == spec
    assert restored.admin_codes == ("101", "1001", "100001")


def test_to_dict_is_json_safe_and_drops_unset_fields():
    import json

    spec = AoiSpec(method="ADMIN0", admin_codes=("206",))
    data = spec.to_dict()

    assert json.loads(json.dumps(data)) == data
    assert data["schema_version"] == AOI_SPEC_SCHEMA_VERSION
    assert "pathname" not in data
    assert "geo_json" not in data


def test_shape_spec_round_trips_the_filter():
    spec = AoiSpec(method="SHAPE", pathname="/data/zones.gpkg", column="class", value="forest")

    restored = AoiSpec.from_dict(spec.to_dict())

    assert restored.shape_data() == {
        "pathname": "/data/zones.gpkg",
        "column": "class",
        "value": "forest",
    }


def test_points_spec_round_trips_every_column():
    spec = AoiSpec(
        method="POINTS",
        pathname="/data/plots.csv",
        id_column="id",
        lat_column="lat",
        lng_column="lon",
    )

    restored = AoiSpec.from_dict(spec.to_dict())

    assert restored.points_data() == {
        "pathname": "/data/plots.csv",
        "id_column": "id",
        "lat_column": "lat",
        "lng_column": "lon",
    }


def test_asset_spec_maps_onto_the_picker_dict():
    spec = AoiSpec(
        method="ASSET",
        asset_id="projects/x/assets/aoi",
        asset_type="TABLE",
        column="region",
        value="north",
    )

    assert spec.asset_data() == {
        "asset_id": "projects/x/assets/aoi",
        "type": "TABLE",
        "column": "region",
        "value": "north",
    }


def test_draw_spec_keeps_the_raw_geojson():
    geo_json = {"type": "FeatureCollection", "features": [{"type": "Feature", "id": "a"}]}
    spec = AoiSpec(method="DRAW", name="plot_a", geo_json=geo_json)

    restored = AoiSpec.from_dict(spec.to_dict())

    assert restored.geo_json == geo_json
    assert restored.name == "plot_a"


def test_geo_json_is_copied_not_shared():
    """A caller mutating its dict must not change what a spec equals or serializes to."""
    geo_json = {"type": "FeatureCollection", "features": []}
    spec = AoiSpec(method="DRAW", geo_json=geo_json)

    payload = spec.to_dict()
    geo_json["features"].append({"type": "Feature"})

    assert payload["geo_json"]["features"] == []


def test_picker_dicts_are_none_for_the_wrong_method():
    spec = AoiSpec(method="ADMIN0", admin_codes=("206",))

    assert spec.shape_data() is None
    assert spec.points_data() is None
    assert spec.asset_data() is None


def test_from_dict_rejects_a_newer_schema():
    with pytest.raises(ValueError, match="schema version"):
        AoiSpec.from_dict({"method": "ADMIN0", "schema_version": AOI_SPEC_SCHEMA_VERSION + 1})


def test_from_dict_requires_a_method():
    with pytest.raises(ValueError, match="method"):
        AoiSpec.from_dict({"schema_version": AOI_SPEC_SCHEMA_VERSION})


def test_spec_is_hashable_and_compares_by_content():
    a = AoiSpec(method="ADMIN0", admin_codes=("206",))
    b = AoiSpec(method="ADMIN0", admin_codes=("206",))

    assert a == b
    assert {a, b} == {a}
