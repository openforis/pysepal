"""Tests for the reusable Solara map legend dataclasses and component."""

import re
from dataclasses import asdict
from pathlib import Path

import solara

from pysepal.solara.components.legend import DiscreteEntry, LegendComponent, LegendData
from tests.test_solara.test_notifications.test_notification_ui_template import (
    needs_node,
    run_vue_script,
)

_TEMPLATE = Path(__file__).resolve().parents[2] / "pysepal" / "solara" / "components" / "Legend.vue"


def _render(**props):
    """Render LegendComponent and return the underlying Vue widget."""
    box, _ = solara.render(LegendComponent(**props), handle_error=False)
    return box.children[0]


def test_discrete_entry_detail_defaults_empty():
    entry = DiscreteEntry(label="Forest", color="#006400")
    assert entry.detail == ""


def test_discrete_entry_detail_roundtrips_through_asdict():
    entry = DiscreteEntry(label="Nival", color="#ff0000", detail="1,234 km² · 12%")
    assert asdict(entry) == {
        "label": "Nival",
        "color": "#ff0000",
        "detail": "1,234 km² · 12%",
    }


def test_legend_data_serializes_items_with_detail_and_empty_color():
    data = LegendData(items=[DiscreteEntry("Total", "", detail="9,999 km² · 100%")])
    payload = asdict(data)
    assert payload["items"][0]["color"] == ""
    assert payload["items"][0]["detail"] == "9,999 km² · 100%"
    assert payload["gradients"] == []


def test_detail_and_empty_color_survive_the_widget_boundary():
    data = LegendData(
        items=[
            DiscreteEntry("Lowland", "#c7e9b4", detail="1,234 km² · 40%"),
            DiscreteEntry("Total", "", detail="3,085 km² · 100%"),
        ]
    )
    items = _render(legend_data=asdict(data)).legend_data["items"]

    assert [item["detail"] for item in items] == ["1,234 km² · 40%", "3,085 km² · 100%"]
    assert items[1]["color"] == ""


def test_selector_props_reach_the_widget():
    options = [{"value": "ndvi", "text": "NDVI"}, {"value": "area", "text": "Pixel area"}]
    widget = _render(
        legend_data=asdict(LegendData(items=[DiscreteEntry("Forest", "#006400")])),
        selector_options=options,
        selected="area",
    )

    assert widget.selector_options == options
    assert widget.selected == "area"


def test_selecting_an_option_calls_back_into_python():
    picked = []
    widget = _render(
        legend_data=asdict(LegendData(items=[DiscreteEntry("Forest", "#006400")])),
        selector_options=[{"value": "ndvi", "text": "NDVI"}, {"value": "area", "text": "Area"}],
        selected="ndvi",
        event_set_selected=picked.append,
    )

    # What the template does on @change: `this.set_selected(value)`.
    widget._handle_custom_msg({"event": "set_selected", "data": "area"}, [])

    assert picked == ["area"]


def test_template_has_no_vue2_only_syntax():
    """A ``props`` block duplicates the traits ipyvue provides as data, which Vue reports."""
    content = _TEMPLATE.read_text()
    assert ">>>" not in content
    assert not re.search(r"^\s*props:", content, re.MULTILINE)


def test_bar_icons_have_pixel_sizes_and_no_theme_props():
    """Named icon sizes scale with the font; the icons take the bar's themed text colour."""
    markup = re.sub(r"<!--.*?-->", "", _TEMPLATE.read_text().split("<script>")[0], flags=re.DOTALL)
    icons = re.findall(r"<v-icon\b([^>]*)>", markup)
    assert icons == [' :size="16"', ' :size="12"']


@needs_node
def test_dark_styling_follows_the_vuetify_theme():
    """``theme.global.current`` is a ref, or already unwrapped when ``$vuetify`` is reactive."""
    dark = run_vue_script(
        _TEMPLATE,
        """
        const shapes = {
          ref: (dark) => ({ theme: { global: { current: { value: { dark } } } } }),
          unwrapped: (dark) => ({ theme: { global: { current: { dark } } } }),
        };
        const out = {};
        for (const [name, shape] of Object.entries(shapes)) {
          out[name] = [true, false].map((d) => makeVm({ $vuetify: shape(d) }).isDark);
        }
        return out;
        """,
    )
    assert dark == {"ref": [True, False], "unwrapped": [True, False]}


@needs_node
def test_the_legend_opens_in_the_collapsed_state_it_is_given():
    """``collapsed=True`` must render collapsed.

    ipyvue calls ``data()`` before the traits exist, so ``created()`` copies it.
    """
    collapsed = run_vue_script(
        _TEMPLATE,
        """
        return [true, false].map((collapsed) => {
          const vm = makeVm({ collapsed });
          options.created.call(vm);
          return vm.isCollapsed;
        });
        """,
    )
    assert collapsed == [True, False]
