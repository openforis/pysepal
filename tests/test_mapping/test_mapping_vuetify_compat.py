"""The map controls build on the Vuetify 3 widgets."""

import ipyleaflet as ipl
import ipyvuetify as v

from pysepal import mapping as sm
from pysepal._sepal_widget import SepalWidget
from pysepal.mapping.draw_control import GeomanDrawControl


def test_sepal_map_builds() -> None:
    """A map with every control builds, and each control uses the expected widgets."""
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

    # the state bar is a Sheet: a SystemBar needs a v-layout parent
    state = m.state.w_state
    assert isinstance(state, SepalWidget)
    assert isinstance(state, v.Sheet)
    assert state.children[1] == state.msg
    state.add_msg("loading", loading=True)
    assert state.progress.indeterminate is True

    # the zoom buttons sit in a plain flex column
    zoom = next(c for c in m.controls if isinstance(c, sm.ZoomControl))
    assert zoom.widget.class_ == "d-flex flex-column"
    assert zoom.widget.children == [zoom.plus, zoom.minus]

    # the map btn shows an outlined small icon
    btn = zoom.plus
    assert btn.variant == "outlined"
    assert btn.children[0].size == "small"
    assert btn.hide() is btn and btn.viz is False

    # the legend card still chains hide/show
    assert m.legend.legend_card.viz is True
    assert m.legend.legend_card.hide() is m.legend.legend_card

    # the fullscreen btn swaps the icon it displays
    fullscreen = next(c for c in m.controls if isinstance(c, sm.FullScreenControl))
    fullscreen.toggle_fullscreen()
    assert fullscreen.w_btn.children[0].children == [f"class:{sm.FullScreenControl.ICONS[1]}"]

    # the inspector stays open when the map is clicked
    assert m.v_inspector.menu.persistent is True

    m.close()

    return


def test_inspector_tree_opens() -> None:
    """The inspector writes its tree for the Treeview template."""
    m = sm.SepalMap(gee=False, vinspector=True)
    m.add(ipl.TileLayer(url="https://example.com/{z}/{x}/{y}.png", name="tiles"))
    m.v_inspector.menu.v_model = True
    m.v_inspector.read_data(type="click", coordinates=[0, 0])

    tree = m.v_inspector.text.children[3]
    assert tree.items[0]["name"] == "tiles"
    # a v-treeview widget renders its empty default slot instead of its items
    assert isinstance(tree, v.VuetifyTemplate)
    assert 'item-title="name"' in tree.template
    assert tree.opened == ["0"]
    values = [leaf["id"] for leaf in tree.items[0]["children"]]
    assert len(values) == len(set(values))

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

    # a radio group would drive the checkboxes too: the radios stand alone
    group = control.group
    table = control.tile.children[0]
    assert isinstance(table, v.Table)
    assert not isinstance(group, v.RadioGroup)
    assert "v-no-border" in table.class_

    row = control.tile.get_children(klass=sm.LayerRow)[0]
    assert isinstance(row.w_checkbox, v.Checkbox)
    assert "v-no-messages" in row.w_slider.class_
    assert row.w_checkbox.hide_details is True
    assert row.w_checkbox.density == "compact"
    assert table.density == "compact"

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
