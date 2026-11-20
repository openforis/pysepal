"""The widget under each runner: Solara, Voilà and JupyterLab.

A JupyterLab reload reconnects to the kernel that holds the widget, so the
view shows the live state. A new page under Solara or Voilà starts a new
kernel, so the app starts fresh: keeping layers across page loads is not a
goal.
"""

import json
from pathlib import Path

import ipywidgets as widgets
import pytest
import solara

INITIAL, ADDED = [-10, 0], [10, 0]


def app():
    # The runners run this body in their own kernel, so it imports what it uses.
    import json

    import ipywidgets as widgets
    from IPython.display import display
    from pysepal_map import GeoJSONSource, Layer, MapState, MapWidget, VectorPaint

    def point(m, layer_id, lng, color):
        feature = {
            "type": "Feature",
            "properties": {},
            "geometry": {"type": "Point", "coordinates": [lng, 0]},
        }
        data = json.dumps({"type": "FeatureCollection", "features": [feature]})
        paint = VectorPaint(stroke=color, fill=color, fill_opacity=1.0, point_radius=8)
        return Layer(layer_id, GeoJSONSource(m.add_payload(data.encode())), paint=paint)

    m = MapWidget(center=(0, 0), zoom=3, height="300px")
    initial = point(m, "initial", -10, "#ff0000")
    m.draw(MapState(layers=(initial,)))

    def add(_):
        m.draw(MapState(layers=(point(m, "added", 10, "#0000ff"), initial)))

    button = widgets.Button(description="add a point")
    button.add_class("psm-add")
    button.on_click(add)
    display(m)
    display(button)
    display(widgets.HTML(f"<span class='psm-model-id'>{m.model_id}</span>"))


@solara.component
def FreshApp():
    """``app`` as a Solara app; each page gets a kernel, so it runs again."""

    def build():
        output = widgets.Output()
        with output:
            app()
        return output

    solara.display(solara.use_memo(build, []))


# Owned circle features within a few px of a place, once the map is idle.
CIRCLES_AT = """async (el, at) => {
    await psmHarness.quiet(el);
    const circles = el.psmMap.getLayersOrder().filter(
        (id) => id.startsWith('psm:') && id.endsWith(':circle'));
    return psmHarness.featuresAt(el, at, circles);
}"""


def mounted_view(page, load_harness):
    """The view the runner displayed, with the probes loaded into its page."""
    page.wait_for_function("document.querySelector('.psm-map')?.psmMap")
    load_harness(page)
    return page.locator(".psm-map").first.element_handle()


def wait_hit(page, el, at, layer):
    page.wait_for_function(
        "([el, at, layer]) => psmHarness.featuresAt(el, at, [layer]) > 0",
        arg=[el, at, layer],
    )


def owned_layers(el):
    return el.evaluate("el => el.psmMap.getLayersOrder().filter((id) => id.startsWith('psm:'))")


def model_id(page):
    return page.locator(".psm-model-id").inner_text()


def add_point(page, el):
    page.locator(".psm-add").click()
    wait_hit(page, el, ADDED, "psm:added:2:circle")


def assert_only_initial(el):
    assert el.evaluate(CIRCLES_AT, INITIAL) == 1
    assert el.evaluate(CIRCLES_AT, ADDED) == 0
    assert {id.rsplit(":", 1)[0] for id in owned_layers(el)} == {"psm:initial:1"}


def test_renders_everywhere(ipywidgets_runner, page_session, load_harness):
    ipywidgets_runner(app)
    el = mounted_view(page_session, load_harness)
    wait_hit(page_session, el, INITIAL, "psm:initial:1:circle")
    assert_only_initial(el)


@pytest.mark.parametrize("ipywidgets_runner", ["jupyter_lab"], indirect=True)
def test_a_jupyterlab_reload_shows_the_live_widget(
    ipywidgets_runner, page_session, load_harness, notebook_path
):
    ipywidgets_runner(app)
    el = mounted_view(page_session, load_harness)
    wait_hit(page_session, el, INITIAL, "psm:initial:1:circle")
    shown = model_id(page_session)
    add_point(page_session, el)

    # Save the notebook with its widget outputs.
    page_session.locator('css=[data-command="docmanager:save"]').first.click()
    saved = []
    for _ in range(750):
        try:
            cells = json.loads(Path(notebook_path).read_text())["cells"]
        except json.JSONDecodeError:
            # Caught while the server is rewriting the file.
            page_session.wait_for_timeout(20)
            continue
        saved = [
            output["data"]["application/vnd.jupyter.widget-view+json"]["model_id"]
            for cell in cells
            for output in cell.get("outputs", [])
            if "application/vnd.jupyter.widget-view+json" in output.get("data", {})
        ]
        if saved:
            break
        page_session.wait_for_timeout(20)
    assert saved and saved[0] == shown

    # The reload reconnects to the same kernel; no cell runs again.
    page_session.reload()
    el = mounted_view(page_session, load_harness)
    wait_hit(page_session, el, ADDED, "psm:added:2:circle")
    wait_hit(page_session, el, INITIAL, "psm:initial:1:circle")
    assert model_id(page_session) == shown


@pytest.mark.parametrize("ipywidgets_runner", ["voila"], indirect=True)
def test_a_new_voila_page_starts_fresh(ipywidgets_runner, page_session, load_harness):
    ipywidgets_runner(app)
    el = mounted_view(page_session, load_harness)
    wait_hit(page_session, el, INITIAL, "psm:initial:1:circle")
    first = model_id(page_session)
    add_point(page_session, el)

    page_session.reload()
    el = mounted_view(page_session, load_harness)
    wait_hit(page_session, el, INITIAL, "psm:initial:1:circle")
    assert model_id(page_session) != first
    assert_only_initial(el)


def test_a_new_solara_page_starts_fresh(solara_server, solara_app, page_session, load_harness):
    with solara_app(f"{__name__}:FreshApp"):
        page_session.goto(solara_server.base_url)
        el = mounted_view(page_session, load_harness)
        wait_hit(page_session, el, INITIAL, "psm:initial:1:circle")
        first = model_id(page_session)
        add_point(page_session, el)

        page_session.reload()
        el = mounted_view(page_session, load_harness)
        wait_hit(page_session, el, INITIAL, "psm:initial:1:circle")
        assert model_id(page_session) != first
        assert_only_initial(el)
    page_session.goto("about:blank")
