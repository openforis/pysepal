"""Test the Zoom Control."""

from pysepal import mapping as sm


def test_init() -> None:
    """Init a zoom control."""
    m = sm.SepalMap()
    m.clear()
    zoom_control = sm.ZoomControl(m)
    m.add(zoom_control)

    assert isinstance(zoom_control, sm.ZoomControl)
    assert zoom_control in m.controls

    return


def test_change_zoom() -> None:
    """Change the zoom of the map."""
    m = sm.SepalMap()
    zoom_control = next(c for c in m.controls if isinstance(c, sm.ZoomControl))
    m.zoom = 10

    zoom_control.zoom(zoom_control.plus)
    assert m.zoom == 11

    zoom_control.zoom(zoom_control.minus)
    assert m.zoom == 10

    return


def test_min_max_zoom() -> None:
    """Check that min and max values are respected."""
    m = sm.SepalMap()
    zoom_control = next(c for c in m.controls if isinstance(c, sm.ZoomControl))

    # click 40 times on plus and then 40 times on minus
    [zoom_control.zoom(zoom_control.plus) for i in range(40)]
    assert m.zoom == m.max_zoom
    [zoom_control.zoom(zoom_control.minus) for i in range(40)]
    assert m.zoom == m.min_zoom

    # same but with a min-max zoom on the map
    m.min_zoom = 5
    m.max_zoom = 18
    [zoom_control.zoom(zoom_control.plus) for i in range(40)]
    assert m.zoom == m.max_zoom
    [zoom_control.zoom(zoom_control.minus) for i in range(40)]
    assert m.zoom == m.min_zoom

    return
