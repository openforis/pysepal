"""Stand-ins for a user drawing on a map, for the AoiView tests."""

import uuid

SQUARE = [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]
HOLE = [[0.2, 0.2], [0.4, 0.2], [0.4, 0.4], [0.2, 0.4], [0.2, 0.2]]


def mount(m, view="a"):
    """Open a view of the map, as the browser does."""
    m._handle_custom_msg({"type": "view_open", "view_id": view, "side": "main"}, [])


def drawn_feature(ring=SQUARE):
    """A polygon as a view reports it, with the properties Terra Draw adds."""
    return {
        "type": "Feature",
        "id": str(uuid.uuid4()),
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "properties": {"mode": "circle", "radiusKilometers": 1.5, "name": "kept"},
    }


def report(m, features=None, *, view="a"):
    """The browser reports a drawing the user made on the current request."""
    m._handle_custom_msg(
        {
            "type": "draw_report",
            "view_id": view,
            "side": "main",
            "request_seq": m.draw_request["seq"],
            "cause": "user",
            "features": [drawn_feature()] if features is None else features,
        },
        [],
    )
