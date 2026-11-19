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
