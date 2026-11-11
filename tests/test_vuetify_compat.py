"""Test the ipyvuetify 1/3 compat helpers on both branches."""

from pathlib import Path

import pytest

from pysepal import _vuetify


@pytest.fixture(params=[False, True], ids=["v2", "v3"])
def major(request, monkeypatch) -> bool:
    """Run a test once per Vuetify major, whatever ipyvuetify is installed."""
    monkeypatch.setattr(_vuetify, "IPYVUETIFY_V3", request.param)
    return request.param


def test_switch_matches_solara() -> None:
    """Check that pysepal and Solara read the installed major the same way."""
    import solara.util

    if not hasattr(solara.util, "IPYVUETIFY_V3"):
        pytest.skip("solara older than 1.61 has no IPYVUETIFY_V3")
    assert _vuetify.IPYVUETIFY_V3 is solara.util.IPYVUETIFY_V3


def test_density(major: bool) -> None:
    """Check the dense flag on both majors."""
    expected = {"density": "compact"} if major else {"dense": True}
    assert _vuetify.density() == expected
    assert _vuetify.density(False) == {}


@pytest.mark.parametrize(
    "name,v2,v3",
    [
        ("small", {"small": True}, {"size": "small"}),
        ("x-small", {"x_small": True}, {"size": "x-small"}),
        ("large", {"large": True}, {"size": "large"}),
        (None, {}, {}),
    ],
)
def test_size(major: bool, name, v2, v3) -> None:
    """Check the size flags on both majors."""
    assert _vuetify.size(name) == (v3 if major else v2)


def test_size_rejects_unknown_name() -> None:
    """Check that a typo fails instead of silently doing nothing."""
    with pytest.raises(ValueError):
        _vuetify.size("tiny")


@pytest.mark.parametrize(
    "flags,v2,v3",
    [
        ({"text": True}, {"text": True}, {"variant": "text"}),
        ({"outlined": True}, {"outlined": True}, {"variant": "outlined"}),
        ({"depressed": True}, {"depressed": True}, {"variant": "flat"}),
        ({"text": True, "outlined": True}, {"text": True, "outlined": True}, {"variant": "text"}),
        ({}, {}, {}),
    ],
)
def test_btn_variant(major: bool, flags, v2, v3) -> None:
    """Check the button style flags on both majors."""
    assert _vuetify.btn_variant(**flags) == (v3 if major else v2)


def test_icon_start(major: bool) -> None:
    """Check the leading icon flag on both majors."""
    assert _vuetify.icon_start() == ({"start": True} if major else {"left": True})


def test_field_variant(major: bool) -> None:
    """Check the text field style on both majors."""
    if major:
        assert _vuetify.field_variant() == {"variant": "underlined"}
        assert _vuetify.field_variant(outlined=True) == {"variant": "outlined"}
    else:
        assert _vuetify.field_variant() == {}
        assert _vuetify.field_variant(outlined=True) == {"outlined": True}


ITEMS = [
    {"header": "H"},
    {"divider": True},
    {"text": "A", "value": "a", "disabled": True},
    {"text": "B", "value": "b"},
    "c",
]


def test_select_items_v2_unchanged(monkeypatch) -> None:
    """Check that Vuetify 2 items pass through as they are."""
    monkeypatch.setattr(_vuetify, "IPYVUETIFY_V3", False)
    assert _vuetify.select_items(ITEMS) == ITEMS


def test_select_items_v3_header_divider_disabled(monkeypatch) -> None:
    """Check the Vuetify 3 spelling of every item shape pysepal uses."""
    monkeypatch.setattr(_vuetify, "IPYVUETIFY_V3", True)
    assert _vuetify.select_items(ITEMS) == [
        {"type": "subheader", "title": "H"},
        {"type": "divider", "title": ""},
        {"title": "A", "value": "a", "props": {"disabled": True}},
        {"title": "B", "value": "b"},
        "c",
    ]


def test_select_items_v3_does_not_mutate(monkeypatch) -> None:
    """Check that the caller's items are left as they were."""
    monkeypatch.setattr(_vuetify, "IPYVUETIFY_V3", True)
    items = [{"text": "A", "value": "a"}]
    _vuetify.select_items(items)
    assert items == [{"text": "A", "value": "a"}]


def test_vuetify_markup(major: bool, tmp_path: Path) -> None:
    """Check that the markup file follows the installed major."""
    stem = tmp_path / "Widget"
    expected = "Widget.v3.vue" if major else "Widget.v2.vue"
    assert _vuetify.vuetify_markup(stem).name == expected


def test_compose_vue_inserts_script_before_style(tmp_path: Path) -> None:
    """Check that the shared script lands between the template and the style."""
    markup = tmp_path / "W.v2.vue"
    markup.write_text("<template><div/></template>\n<style>.a {}</style>\n")
    script = tmp_path / "W.js"
    script.write_text("export default {};\n")

    composed = _vuetify.compose_vue(markup, script)

    assert composed.index("</template>") < composed.index("<script>")
    assert composed.index("</script>") < composed.index("<style>")
    assert "export default {};" in composed


def test_compose_vue_without_style(tmp_path: Path) -> None:
    """Check that the script is appended when the markup has no style block."""
    markup = tmp_path / "W.v3.vue"
    markup.write_text("<template><div/></template>\n")
    script = tmp_path / "W.js"
    script.write_text("export default {};\n")

    assert _vuetify.compose_vue(markup, script).rstrip().endswith("</script>")
