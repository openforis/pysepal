"""The map controls and the theme follow the state."""

import ipywidgets as widgets
from IPython.display import display
from pysepal_map import Controls, MapState, MapWidget

ZOOM_IN = ".maplibregl-ctrl-zoom-in"
FULLSCREEN = ".maplibregl-ctrl-fullscreen"
COMPASS = ".maplibregl-ctrl-compass"


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
    widget.draw(MapState(controls=Controls(zoom=False, fullscreen=True)))
    wait_counts(page_session, [0, 1, 0])
    widget.draw(MapState(controls=Controls(zoom=True, fullscreen=False)))
    wait_counts(page_session, [1, 0, 0])
    widget.draw(MapState(controls=Controls(zoom=False, fullscreen=False)))
    wait_counts(page_session, [0, 0, 0])
    widget.draw(MapState())
    wait_counts(page_session, [1, 1, 0])


def test_dark_theme_sets_the_class(solara_test, page_session):
    widget = MapWidget()
    display(widget)
    page_session.locator(".psm-map canvas").wait_for()
    assert not page_session.locator(".psm-map.psm-dark").count()
    widget.draw(MapState(theme="dark"))
    page_session.locator(".psm-map.psm-dark").wait_for()
    widget.draw(MapState(theme="light"))
    page_session.wait_for_function(
        "!document.querySelector('.psm-map').classList.contains('psm-dark')"
    )


def test_dark_controls_use_the_dark_surface(solara_test, page_session):
    widget = MapWidget()
    widget.draw(MapState(theme="dark"))
    display(widget)
    button = page_session.locator(f".psm-dark {ZOOM_IN}")
    button.wait_for()
    background, icon_filter = button.evaluate(
        "el => [getComputedStyle(el).backgroundColor,"
        " getComputedStyle(el.querySelector('span')).filter]"
    )
    assert background == "rgb(30, 30, 30)"
    assert "invert" in icon_filter


def test_map_has_a_width_inside_an_hbox(solara_test, page_session):
    display(widgets.HBox([MapWidget(height="200px")]))
    page_session.locator(".psm-map canvas.maplibregl-canvas").wait_for()
    page_session.wait_for_function(
        "document.querySelector('.psm-map').getBoundingClientRect().width > 100"
        " && document.querySelector('.psm-map canvas').clientWidth > 100"
    )
