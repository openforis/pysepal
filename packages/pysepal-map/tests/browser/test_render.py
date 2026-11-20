from urllib.parse import urlsplit

import ipywidgets as widgets
from IPython.display import display

from pysepal_map import MapWidget


def test_map_canvas_appears(solara_test, page_session):
    display(MapWidget(height="300px"))
    page_session.locator(".psm-map canvas.maplibregl-canvas").wait_for()
    assert page_session.locator(".psm-map").bounding_box()["height"] == 300


def test_no_request_leaves_the_machine(solara_test, page_session):
    urls = []
    page_session.on("request", lambda r: urls.append(r.url))
    display(MapWidget())
    page_session.locator(".psm-map canvas.maplibregl-canvas").wait_for()
    local = ("127.0.0.1", "localhost", "::1")
    external = [
        u
        for u in urls
        if urlsplit(u).scheme in ("http", "https") and urlsplit(u).hostname not in local
    ]
    assert external == []


def test_map_fills_a_box_that_grows(solara_test, page_session):
    box = widgets.Box([MapWidget(height="100%")], layout=widgets.Layout(height="0px"))
    display(box)
    page_session.locator(".psm-map").wait_for(state="attached")
    box.layout.height = "250px"
    page_session.wait_for_function("document.querySelector('.psm-map canvas')?.clientHeight === 250")
