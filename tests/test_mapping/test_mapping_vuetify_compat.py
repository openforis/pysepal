"""The map controls build on both ipyvuetify majors without pysepal.sepalwidgets."""

import subprocess
import sys
from pathlib import Path

import ipyleaflet as ipl
import ipyvuetify as v

from pysepal import mapping as sm
from pysepal._sepal_widget import SepalWidget
from pysepal._vuetify import IPYVUETIFY_V3
from pysepal.mapping.draw_control import GeomanDrawControl

REPO_ROOT = Path(__file__).parents[2]


def test_import_mapping_v3_without_sepalwidgets() -> None:
    """Importing the map package loads no module of the deprecated widget package."""
    code = (
        "import sys, pysepal.mapping\n"
        "print('ORIGIN', pysepal.mapping.__file__)\n"
        "print('LEGACY', [m for m in sys.modules if m.startswith('pysepal.sepalwidgets')])"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], check=True, capture_output=True, text=True, cwd=REPO_ROOT
    )
    lines = result.stdout.splitlines()

    assert f"ORIGIN {REPO_ROOT / 'pysepal' / 'mapping' / '__init__.py'}" in lines
    assert "LEGACY []" in lines


def test_sepal_map_builds() -> None:
    """A map with every control builds, and each control uses the widgets of the major."""
    m = sm.SepalMap(gee=False, dc=True, vinspector=True, statebar=True, fullscreen_control=True)
    m.add_legend(legend_dict={"forest": "green", "water": "blue"})
    m.add(sm.MenuControl("fa-solid fa-folder", v.Card(children=["content"]), m=m))

    controls = {type(c) for c in m.controls}
    expected = {
        sm.ZoomControl,
        sm.LayersControl,
        sm.InspectorControl,
        sm.LayerStateControl,
        sm.FullScreenControl,
        sm.LegendControl,
        sm.MenuControl,
        GeomanDrawControl,
    }
    assert expected <= controls

    # the state bar keeps its traits on both majors
    state = m.state.w_state
    assert isinstance(state, SepalWidget)
    assert isinstance(state, v.Sheet if IPYVUETIFY_V3 else v.SystemBar)
    assert state.children[1] == state.msg
    state.add_msg("loading", loading=True)
    assert state.progress.indeterminate is True

    # the zoom buttons sit in a plain flex column
    zoom = next(c for c in m.controls if isinstance(c, sm.ZoomControl))
    assert zoom.widget.class_ == "d-flex flex-column"
    assert zoom.widget.children == [zoom.plus, zoom.minus]

    # the map btn shows an outlined small icon
    btn = zoom.plus
    if IPYVUETIFY_V3:
        assert btn.variant == "outlined"
        assert btn.children[0].size == "small"
    else:
        assert btn.outlined is True
        assert btn.children[0].small is True
    assert btn.hide() is btn and btn.viz is False

    # the legend card still chains hide/show
    assert m.legend.legend_card.viz is True
    assert m.legend.legend_card.hide() is m.legend.legend_card

    # the fullscreen btn swaps the icon it displays
    fullscreen = next(c for c in m.controls if isinstance(c, sm.FullScreenControl))
    fullscreen.toggle_fullscreen()
    prefix = "class:" if IPYVUETIFY_V3 else ""
    assert fullscreen.w_btn.children[0].children == [f"{prefix}{sm.FullScreenControl.ICONS[1]}"]

    # the inspector stays open when the map is clicked
    menu = m.v_inspector.menu
    if IPYVUETIFY_V3:
        assert menu.persistent is True
    else:
        assert menu.close_on_click is False

    m.close()

    return


def test_inspector_tree_opens_on_both_majors() -> None:
    """The inspector writes its tree for the Treeview of the installed major."""
    m = sm.SepalMap(gee=False, vinspector=True)
    m.add(ipl.TileLayer(url="https://example.com/{z}/{x}/{y}.png", name="tiles"))
    m.v_inspector.menu.v_model = True
    m.v_inspector.read_data(type="click", coordinates=[0, 0])

    tree = m.v_inspector.text.children[3]
    assert tree.items[0]["name"] == "tiles"
    if IPYVUETIFY_V3:
        # a v-treeview widget renders its empty default slot instead of its items
        assert isinstance(tree, v.VuetifyTemplate)
        assert 'item-title="name"' in tree.template
        assert tree.opened == ["0"]
        values = [leaf["id"] for leaf in tree.items[0]["children"]]
        assert len(values) == len(set(values))
    else:
        assert isinstance(tree, v.Treeview)
        assert tree.dense is True
        assert tree.open_ == ["0"]

    m.close()

    return


def test_layers_control_toggles_visibility() -> None:
    """The checkbox hides a layer, the slider sets its opacity and a radio picks the basemap."""
    m = ipl.Map()
    second_base = ipl.TileLayer(url="https://example.com/{z}/{x}/{y}.png", name="other", base=True)
    second_base.visible = False
    m.add(second_base)
    layer = ipl.TileLayer(url="https://example.com/{z}/{x}/{y}.png", name="tiles")
    m.add(layer)
    control = sm.LayersControl(m)

    # a Vuetify 3 radio group would drive the checkboxes too: there the radios stand alone
    group = control.group
    if IPYVUETIFY_V3:
        table = control.tile.children[0]
        assert isinstance(table, v.Table)
        assert not isinstance(group, v.RadioGroup)
    else:
        assert control.tile.children[0] is group
        assert isinstance(group, v.RadioGroup)
        table = group.children[0]
        assert isinstance(table, v.SimpleTable)
    assert "v-no-border" in table.class_

    row = control.tile.get_children(klass=sm.LayerRow)[0]
    assert isinstance(row.w_checkbox, v.Checkbox if IPYVUETIFY_V3 else v.SimpleCheckbox)
    assert "v-no-messages" in row.w_slider.class_
    if IPYVUETIFY_V3:
        assert row.w_checkbox.hide_details is True
        assert row.w_checkbox.density == "compact"
        assert table.density == "compact"
    else:
        assert table.dense is True

    # the checkbox drives the layer visibility both ways
    row.w_checkbox.v_model = False
    assert layer.visible is False
    assert row.w_slider.disabled is True
    layer.visible = True
    assert row.w_checkbox.v_model is True

    # the slider drives the opacity
    row.w_slider.v_model = 0.5
    assert layer.opacity == 0.5

    # one radio per basemap, the group keeps a single one active
    bases = {r.children[0].children[0]: r for r in control.tile.get_children(klass=sm.BaseRow)}
    default_name = next(lyr.name for lyr in m.layers if lyr.base and lyr is not second_base)
    default_layer = next(lyr for lyr in m.layers if lyr.name == default_name)
    assert group.v_model == default_name
    assert bases[default_name].w_radio.active is True
    assert bases["other"].w_radio.active is False
    if IPYVUETIFY_V3:
        # each radio sits alone in a group whose v_model mirrors the radio
        solo = {name: row.children[2].children[0] for name, row in bases.items()}
        assert isinstance(solo["other"], v.RadioGroup)
        assert solo[default_name].v_model == default_name
        assert solo["other"].v_model is None

        # a click selects a radio through its group
        solo["other"].v_model = "other"
        assert group.v_model == "other"
        assert second_base.visible is True
        assert solo[default_name].v_model is None
        group.v_model = default_name

    # selecting from the frontend (the group v_model) switches the basemap
    group.v_model = "other"
    assert second_base.visible is True
    assert default_layer.visible is False

    # and showing a basemap from python moves the selection
    default_layer.visible = True
    assert group.v_model == default_name
    assert second_base.visible is False

    control.close()

    return
