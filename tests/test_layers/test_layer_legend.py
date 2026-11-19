"""Tests for legend derivation."""

from pysepal.layers import (
    RasterStyle,
    VectorStyle,
    derive_legend,
    legend_from_asset_viz,
)


def test_class_colors_make_items():
    legend = derive_legend(
        RasterStyle(class_colors={1: "#00ff00", 2: "#0000ff"}, class_labels={1: "Forest"})
    )
    assert [(i.label, i.color) for i in legend.items] == [("Forest", "#00ff00"), ("2", "#0000ff")]


def test_palette_makes_gradient():
    legend = derive_legend(RasterStyle(min=0, max=1, palette=["#000000", "#ffffff"]), title="NDVI")
    assert legend.gradients[0].colors == ["#000000", "#ffffff"]
    assert legend.gradients[0].labels == ["0", "1"]
    assert legend.title == "NDVI"


def test_colormap_makes_gradient_from_matplotlib():
    legend = derive_legend(RasterStyle(min=0, max=10, colormap="viridis"))
    assert len(legend.gradients[0].colors) >= 2 and legend.gradients[0].colors[0].startswith("#")


def test_multiband_without_palette_has_no_legend():
    assert derive_legend(RasterStyle(bands=[3, 2, 1])) is None


def test_vector_single_chip_uses_default_color():
    legend = derive_legend(VectorStyle(), title="Roads", default_color="#123456")
    assert [(i.label, i.color) for i in legend.items] == [("Roads", "#123456")]


def test_vector_prefers_fill_then_stroke():
    both = VectorStyle(stroke="#111111", fill="#222222")
    assert derive_legend(both, title="a").items[0].color == "#222222"
    assert derive_legend(VectorStyle(stroke="#111111"), title="a").items[0].color == "#111111"


def test_asset_viz_categorical():
    viz = {
        "type": "categorical",
        "values": [1, 3],
        "labels": ["a", "b"],
        "palette": ["#111111", "#333333"],
    }
    assert [i.label for i in legend_from_asset_viz(viz).items] == ["a", "b"]


def test_asset_viz_continuous_and_unsupported():
    viz = {"type": "continuous", "palette": ["#000000", "ffffff"], "min": [0], "max": [5]}
    legend = legend_from_asset_viz(viz, title="T")
    assert legend.gradients[0].labels == ["0", "5"]
    assert legend.gradients[0].colors == ["#000000", "#ffffff"]
    assert legend_from_asset_viz({"type": "rgb", "bands": ["a", "b", "c"]}) is None
    assert legend_from_asset_viz({}) is None
