"""Tests for the reusable Solara map legend dataclasses and component."""

import re
from dataclasses import asdict
from pathlib import Path

import solara

from pysepal.message import msg
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


def test_the_bar_is_one_menu_icon_with_a_pixel_size_and_no_theme_props():
    """Named icon sizes scale with the font; the icon takes the bar's themed text colour."""
    markup = re.sub(r"<!--.*?-->", "", _TEMPLATE.read_text().split("<script>")[0], flags=re.DOTALL)
    icons = re.findall(r"<v-icon\b([^>]*)>([^<]*)<", markup)
    assert icons == [(' :size="16"', "mdi-menu")]
    # the name is the host's to show, where the card cannot open
    assert "display: none" in _rule(".sepal-legend__bar-title")


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


_DATA = {"gradients": [], "items": [{"label": "a", "color": "#fff", "detail": ""}]}

_OPTIONS = [
    {"value": "forest", "text": "Forest cover 2024"},
    {"value": "loss", "text": "Tree cover loss"},
    {"value": "gain", "text": "Gain"},
]


def _markup() -> str:
    """The template, with each ``{{ expression }}`` on one line as prettier may wrap it."""
    markup = _TEMPLATE.read_text().split("<script>")[0]
    return re.sub(r"\{\{\s*(.*?)\s*\}\}", r"{{ \1 }}", markup, flags=re.DOTALL)


def _rule(selector: str) -> str:
    """The body of the stylesheet rule whose selector is exactly ``selector``."""
    style = re.sub(
        r"/\*.*?\*/", "", _TEMPLATE.read_text().split("<style scoped>")[1], flags=re.DOTALL
    )
    rules = {m.group(1).strip(): m.group(2) for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", style)}
    assert selector in rules, f"no CSS rule for {selector}"
    return rules[selector]


def test_placement_follows_inline_unless_given():
    assert _render(legend_data=_DATA).placement == "viewport"
    assert _render(legend_data=_DATA, inline=True).placement == "inline"
    assert _render(legend_data=_DATA, inline=True, placement="map").placement == "map"


@needs_node
def test_map_placement_renders_in_flow():
    """The map slot positions the card; the card fills at most the slot, its bar under the body."""
    classes = run_vue_script(
        _TEMPLATE,
        """
        return ["map", "inline", "viewport"].map((placement) => makeVm({ placement }).rootClasses);
        """,
    )
    assert classes[0]["sepal-legend--map"] is True
    assert classes[0]["sepal-legend--inline"] is False
    assert classes[1]["sepal-legend--inline"] is True
    assert not classes[2]["sepal-legend--map"] and not classes[2]["sepal-legend--inline"]

    rule = _rule(".sepal-legend.sepal-legend--map")
    for declaration in (
        "position: static",
        "transform: none",
        "max-width: 100%",
        "max-height: 100%",
    ):
        assert declaration in rule
    # The padding counts within the cap, or the card ends up narrower than its content.
    body = _rule(".sepal-legend.sepal-legend--map > .sepal-legend__body")
    assert "box-sizing: border-box" in body
    assert "max-width: min(380px, 100%)" in body
    # The gradient asks for 200px but yields to a narrower slot.
    bar = _rule(".sepal-legend__gradient-bar")
    assert "width: 200px" in bar and "max-width: 100%" in bar
    assert _markup().index('class="sepal-legend__body"') < _markup().index(
        'class="sepal-legend__bar"'
    )


@needs_node
def test_title_with_several_layers():
    shown = run_vue_script(
        _TEMPLATE,
        f"""
        const vm = makeVm({{ selector_options: {_OPTIONS!r}, selected: "loss", title: "ignored" }});
        return [vm.showSelector, vm.showTitle, vm.displayTitle];
        """,
    )
    assert shown == [True, False, "Tree cover loss"]

    selector = _markup().split('class="sepal-legend__selector"')[1].split("</select>")[0]
    assert "{{ displayTitle }}" in selector
    assert "countText" not in _TEMPLATE.read_text()
    assert "text-overflow: ellipsis" in _rule(".sepal-legend__selector-text")


@needs_node
def test_single_layer_shows_its_title():
    shown = run_vue_script(
        _TEMPLATE,
        """
        const option = [{ value: "a", text: "NDVI" }];
        const vms = [
          makeVm({ selector_options: option, selected: "a", title: "NDVI 2024" }),
          makeVm({ title: "Elevation" }),
          makeVm({ selector_options: option, selected: "a" }),
          makeVm({}),
        ];
        return vms.map((vm) => [vm.showSelector, vm.showTitle, vm.displayTitle]);
        """,
    )
    assert shown == [
        [False, True, "NDVI 2024"],
        [False, True, "Elevation"],
        [False, True, "NDVI"],
        [False, False, ""],
    ]
    assert "{{ displayTitle }}" in _markup().split('class="sepal-legend__title"')[1]


@needs_node
def test_the_bar_label_names_the_layer():
    shown = run_vue_script(
        _TEMPLATE,
        f"""
        const labels = {{ show: "Show legend", hide: "Hide legend" }};
        const named = [true, false].map((collapsed) => {{
          const vm = makeVm({{ collapsed, labels, selector_options: {_OPTIONS!r}, selected: "gain" }});
          options.created.call(vm);
          return vm.barLabel;
        }});
        const bare = makeVm({{ collapsed: true, labels }});
        options.created.call(bare);
        return [...named, bare.barLabel];
        """,
    )
    assert shown == ["Show legend: Gain", "Hide legend: Gain", "Show legend"]
    bar = _markup().split('class="sepal-legend__bar"')[1].split(">")[0]
    assert ':title="barLabel"' in bar and ':aria-label="barLabel"' in bar

    # Hidden, so a host can show it, e.g. in a map area too narrow to open.
    bar = _markup().split('class="sepal-legend__bar"')[1]
    assert "{{ displayTitle }}" in bar.split("sepal-legend__bar-title")[1]
    assert "text-overflow: ellipsis" in _rule(".sepal-legend__bar-title")


def test_labels_default_to_messages():
    expected = {key: msg(f"legend.{key}") for key in ("choose", "show", "hide")}
    assert _render(legend_data=_DATA).labels == expected
    assert expected == {
        "choose": "Choose which layer legend to show",
        "show": "Show legend",
        "hide": "Hide legend",
    }
    assert _render(legend_data=_DATA, labels={"show": "Montrer"}).labels == {
        **expected,
        "show": "Montrer",
    }

    for english in expected.values():
        assert english not in _markup()
    for key in ("choose", "show", "hide"):
        assert f"strings.{key}" in _TEMPLATE.read_text()


def test_title_reaches_the_widget():
    assert _render(legend_data=_DATA, title="Forest").title == "Forest"


def test_long_legends_scroll_inside_the_card():
    """The title row stays put while the content scrolls, under a cap per placement."""
    content = _rule(".sepal-legend__content")
    assert "overflow-y: auto" in content
    assert "min-height: 0" in content
    assert "max-height: 40vh" in _rule(".sepal-legend__body")
    # In the map the slot caps the card, and the body shrinks into it.
    assert "min-height: 0" in _rule(".sepal-legend.sepal-legend--map")
    assert "flex-shrink: 0" in _rule(".sepal-legend__bar")


@needs_node
def test_a_gradient_titled_like_the_layer_shows_the_name_once():
    """A legend derived from a style titles its gradient with the layer's name."""
    shown = run_vue_script(
        _TEMPLATE,
        f"""
        const legend_data = {{
          gradients: [{{ colors: ["#000", "#fff"], labels: ["0", "1"], title: "Gain" }}],
          items: [],
        }};
        return [
          makeVm({{ legend_data, title: "Gain" }}),
          makeVm({{ legend_data, title: "Elevation" }}),
          makeVm({{ legend_data, selector_options: {_OPTIONS!r}, selected: "gain" }}),
          makeVm({{ legend_data, selector_options: {_OPTIONS!r}, selected: "loss" }}),
          makeVm({{ legend_data }}),
        ].map((vm) => vm.parsedGradients[0].title);
        """,
    )
    assert shown == ["", "Gain", "", "Gain", "Gain"]
