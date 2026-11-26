"""The map controls and the theme follow the state."""

import ipyvue
import ipywidgets as widgets
from IPython.display import display

from mapframe import Controls, MapState, MapWidget

ZOOM_IN = ".maplibregl-ctrl-zoom-in"
FULLSCREEN = ".maplibregl-ctrl-fullscreen"
COMPASS = ".maplibregl-ctrl-compass"
FULLSCREEN_ROOT = "[data-mapframe-fullscreen-root]"


def wait_corner(page, corner, before):
    """Wait until the fullscreen root holds ``corner``'s current height, not ``before``.

    Returns that height in px.
    """
    handle = page.wait_for_function(
        """([selector, corner, before]) => {
            const root = document.querySelector(selector);
            const el = root?.querySelector(`.maplibregl-ctrl-${corner}`);
            const published = root?.style.getPropertyValue(`--mapframe-controls-${corner}`);
            return el && published === `${el.offsetHeight}px` && published !== before
                && published;
        }""",
        arg=[FULLSCREEN_ROOT, corner, before],
    )
    return handle.json_value()


def wait_counts(page, expected):
    page.wait_for_function(
        "([zoom, full, compass]) =>"
        f" document.querySelectorAll('{ZOOM_IN}').length === zoom"
        f" && document.querySelectorAll('{FULLSCREEN}').length === full"
        f" && document.querySelectorAll('{COMPASS}').length === compass",
        arg=expected,
    )


def test_controls_follow_state(solara_test, page_session):
    widget = MapWidget()
    display(widget)
    wait_counts(page_session, [1, 1, 0])
    widget.publish(MapState(controls=Controls(zoom=False, fullscreen=True)))
    wait_counts(page_session, [0, 1, 0])
    widget.publish(MapState(controls=Controls(zoom=True, fullscreen=False)))
    wait_counts(page_session, [1, 0, 0])
    widget.publish(MapState(controls=Controls(zoom=False, fullscreen=False)))
    wait_counts(page_session, [0, 0, 0])
    widget.publish(MapState())
    wait_counts(page_session, [1, 1, 0])


def test_corner_heights_follow_the_controls(solara_test, page_session):
    widget = MapWidget()
    root = {"data-mapframe-fullscreen-root": ""}
    display(ipyvue.Html(tag="div", attributes=root, children=[widget]))
    with_fullscreen = wait_corner(page_session, "top-left", "")
    marks = page_session.evaluate(
        f"""() => [document.querySelector('{FULLSCREEN_ROOT}').getAttribute('data-mapframe-controls'),
            document.querySelector('.mapframe-map').style.getPropertyValue('--mapframe-controls-top-left')]"""
    )
    assert marks[0] and marks[1] == ""

    widget.publish(MapState(controls=Controls(fullscreen=False)))
    alone = wait_corner(page_session, "top-left", with_fullscreen)
    assert int(alone[:-2]) < int(with_fullscreen[:-2])
    session = widget.draw.begin(("polygon", "point"))
    with_tools = wait_corner(page_session, "top-left", alone)
    assert int(with_tools[:-2]) > int(alone[:-2])
    session.end()
    assert wait_corner(page_session, "top-left", with_tools) == alone

    scale = wait_corner(page_session, "bottom-left", "")
    widget.publish(MapState(controls=Controls(fullscreen=False, coordinates=True)))
    page_session.locator(".mapframe-coordinates").wait_for(state="attached")
    # One row: the readout sits beside the scale and the attribution, so the
    # corner, and what clears it, keeps its height; the readout keeps its place
    # while the pointer is off the map.
    readout = wait_corner(page_session, "bottom-left", "")
    assert readout == scale
    box = page_session.locator(".mapframe-map canvas").bounding_box()
    center = [box["x"] + box["width"] / 2, box["y"] + box["height"] / 2]
    # Solara can briefly lay a progress spinner over the page as a test starts.
    page_session.wait_for_function(
        "([x, y]) => document.elementFromPoint(x, y)?.closest('.mapframe-map')", arg=center
    )
    page_session.mouse.move(*center)
    page_session.wait_for_function("document.querySelector('.mapframe-coordinates').textContent")
    assert wait_corner(page_session, "bottom-left", "") == readout


def test_dark_theme_sets_the_class(solara_test, page_session):
    widget = MapWidget()
    display(widget)
    page_session.locator(".mapframe-map canvas").wait_for()
    assert not page_session.locator(".mapframe-map.mapframe-dark").count()
    widget.publish(MapState(theme="dark"))
    page_session.locator(".mapframe-map.mapframe-dark").wait_for()
    widget.publish(MapState(theme="light"))
    page_session.wait_for_function(
        "!document.querySelector('.mapframe-map').classList.contains('mapframe-dark')"
    )


def test_dark_controls_use_the_dark_surface(solara_test, page_session):
    widget = MapWidget()
    widget.publish(MapState(theme="dark"))
    display(widget)
    button = page_session.locator(f".mapframe-dark {ZOOM_IN}")
    button.wait_for()
    background, color, border, icon_filter = button.evaluate(
        "el => [getComputedStyle(el).backgroundColor, getComputedStyle(el).color,"
        " getComputedStyle(el.parentElement).boxShadow,"
        " getComputedStyle(el.querySelector('span')).filter]"
    )
    assert background == "rgb(30, 30, 30)"
    assert color == "rgb(255, 255, 255)"
    assert "rgb(66, 66, 66)" in border
    assert "invert" in icon_filter


def test_map_has_a_width_inside_an_hbox(solara_test, page_session):
    display(widgets.HBox([MapWidget(height="200px")]))
    page_session.locator(".mapframe-map canvas.maplibregl-canvas").wait_for()
    page_session.wait_for_function(
        "document.querySelector('.mapframe-map').getBoundingClientRect().width > 100"
        " && document.querySelector('.mapframe-map canvas').clientWidth > 100"
    )


def test_explicit_height_holds_inside_a_taller_vbox(solara_test, page_session):
    box = widgets.VBox([MapWidget(height="200px")], layout=widgets.Layout(height="500px"))
    display(box)
    page_session.locator(".mapframe-map canvas.maplibregl-canvas").wait_for()
    assert page_session.locator(".mapframe-map").bounding_box()["height"] == 200


def test_the_globe_button_turns_both_compare_maps_into_a_globe(solara_test, page_session):
    widget = MapWidget()
    widget.publish(MapState(compare=True, controls=Controls(globe=True)))
    display(widget)
    page_session.wait_for_function(
        "document.querySelector('.mapframe-map')?.mapframeCompare?.map.isStyleLoaded()"
    )
    projections = (
        "el => [el.mapframeMap.getProjection()?.type ?? 'mercator',"
        " el.mapframeCompare.map.getProjection()?.type ?? 'mercator']"
    )
    el = page_session.locator(".mapframe-map")
    page_session.locator(".maplibregl-ctrl-globe").click()
    page_session.wait_for_function(
        "(() => { const el = document.querySelector('.mapframe-map');"
        " return el.mapframeCompare.map.getProjection()?.type === 'globe'; })()"
    )
    assert el.evaluate(projections) == ["globe", "globe"]

    # Without the button nothing could take the view off the globe.
    widget.publish(MapState(compare=True))
    page_session.wait_for_function(
        "!document.querySelector('.maplibregl-ctrl-globe, .maplibregl-ctrl-globe-enabled')"
    )
    page_session.wait_for_function(
        "(() => { const el = document.querySelector('.mapframe-map');"
        " return el.mapframeCompare.map.getProjection()?.type === 'mercator'; })()"
    )
    assert el.evaluate(projections) == ["mercator", "mercator"]


def test_a_globe_compare_view_applies_publishes_after_its_styles_are_rebuilt(
    solara_test, page_session
):
    widget = MapWidget()
    widget.publish(MapState(compare=True, controls=Controls(globe=True)))
    display(widget)
    page_session.wait_for_function(
        "document.querySelector('.mapframe-map')?.mapframeCompare?.map.isStyleLoaded()"
    )
    page_session.locator(".maplibregl-ctrl-globe").click()
    on_globe = (
        "(() => { const el = document.querySelector('.mapframe-map');"
        " return el.mapframeCompare.map.isStyleLoaded()"
        " && el.mapframeCompare.map.getProjection()?.type === 'globe'; })()"
    )
    page_session.wait_for_function(on_globe)

    # MapLibre rebuilds both styles from snapshots after a worker restart, the main one first.
    page_session.locator(".mapframe-map").evaluate(
        "el => { el.mapframeMap._handleWorkersRestarted();"
        " el.mapframeCompare.map._handleWorkersRestarted(); }"
    )
    widget.publish(MapState(compare=True, controls=Controls(globe=True), theme="dark"))
    page_session.wait_for_function(
        "r => document.querySelector('.mapframe-map')?.dataset.mapframeRevision === r",
        arg=str(widget.state["revision"]),
    )
    page_session.wait_for_function(on_globe)


def test_the_projection_reaches_every_view_and_comes_back_from_a_click(solara_test, page_session):
    widget = MapWidget()
    widget.publish(MapState(controls=Controls(globe=True)))
    widget.set_projection("globe")
    display(widget)
    types = (
        "n => { const maps = [...document.querySelectorAll('.mapframe-map')].map(el => el.mapframeMap);"
        " return maps.length === n && maps.every(m => m.isStyleLoaded())"
        " ? maps.map(m => m.getProjection()?.type ?? 'mercator') : null; }"
    )
    page_session.wait_for_function(f"({types})(1)?.[0] === 'globe'")

    page_session.locator(".maplibregl-ctrl-globe-enabled").click()
    for _ in range(500):
        if widget.projection == "mercator":
            break
        page_session.wait_for_timeout(20)
    assert widget.projection == "mercator"

    widget.set_projection("globe")
    display(widget)
    page_session.wait_for_function(f"({types})(2)?.join() === 'globe,globe'")
