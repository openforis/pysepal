"""use_sepal_map builds a map in the component that owns it, and closes it there."""

import solara
from pysepal_map import widget

from pysepal.mapping import SepalMap
from pysepal.solara import use_sepal_map

# Each test links its maps in a group of its own: the process scope is shared, and
# maps that other tests built and never closed stay in theirs.


def closed(m: SepalMap) -> bool:
    return m.comm is None


def report_camera(m: SepalMap, center: tuple, zoom: float) -> None:
    """What a mounted view sends when the user moves it."""
    m._handle_custom_msg({"type": "view_open", "view_id": "v", "side": "main"}, [])
    m._handle_custom_msg(
        {
            "type": "view_report",
            "view_id": "v",
            "request_seq": m.view_request["seq"],
            "cause": "user",
            "center": list(center),
            "zoom": zoom,
            "bounds": [-1, -1, 1, 1],
        },
        [],
    )


def test_a_rerender_keeps_the_map():
    built = []
    tick = solara.reactive(0)

    @solara.component
    def Owner():
        tick.value  # read, so that a change rerenders
        built.append(use_sepal_map(lambda: SepalMap(gee=False), []))

    _, rc = solara.render(Owner(), handle_error=False)
    tick.set(1)

    assert len(built) == 2 and built[0] is built[1]
    assert not closed(built[0])
    rc.close()


def test_the_map_closes_on_unmount():
    built = []
    shown = solara.reactive(True)

    @solara.component
    def Owner():
        built.append(use_sepal_map(lambda: SepalMap(gee=False), []))

    @solara.component
    def Page():
        if shown.value:
            Owner()

    _, rc = solara.render(Page(), handle_error=False)
    assert not closed(built[0])

    shown.set(False)

    assert closed(built[0])
    rc.close()


def test_a_dependency_change_closes_the_old_map():
    built = []
    source = solara.reactive("a")

    @solara.component
    def Owner():
        built.append(use_sepal_map(lambda: SepalMap(gee=False), [source.value]))

    _, rc = solara.render(Owner(), handle_error=False)
    source.set("b")

    old, new = built[0], built[-1]
    assert old is not new
    assert closed(old) and not closed(new)
    rc.close()
    assert closed(new)


def test_a_closed_map_leaves_its_link_group():
    built = []
    shown = solara.reactive(True)

    @solara.component
    def Owner():
        built.append(use_sepal_map(lambda: SepalMap(gee=False, link_group="leaves"), []))

    @solara.component
    def Page():
        if shown.value:
            Owner()

    _, rc = solara.render(Page(), handle_error=False)
    m = built[0]
    token = m._link["group"]
    assert m in widget._LINK_MEMBERS[token]

    shown.set(False)

    assert m.link_group is None
    assert token not in widget._LINK_MEMBERS
    rc.close()


def test_a_hot_reload_closes_the_map_so_the_next_one_opens_at_its_own_center():
    """Hot reload keeps the kernel, so the link scope too, but closes the render context."""
    built = []

    @solara.component
    def Owner():
        built.append(
            use_sepal_map(
                lambda: SepalMap(gee=False, link_group="reload", center=(10, 20), zoom=4), []
            )
        )

    _, rc = solara.render(Owner(), handle_error=False)
    report_camera(built[0], center=(-50.0, -10.0), zoom=7.0)
    rc.close()

    assert closed(built[0])

    _, rc = solara.render(Owner(), handle_error=False)
    reloaded = built[-1]
    assert reloaded is not built[0]
    assert (reloaded.view_request["center"], reloaded.view_request["zoom"]) == ([10, 20], 4)
    rc.close()
