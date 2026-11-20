"""The MapLibre map widget."""

from pathlib import Path

import anywidget
import traitlets

_STATIC = Path(__file__).parent / "static"


class MapWidget(anywidget.AnyWidget):
    """A MapLibre map whose persistent configuration lives in ``state``."""

    _esm = _STATIC / "widget.js"
    _css = _STATIC / "widget.css"

    state = traitlets.Dict().tag(sync=True)
    view = traitlets.Dict().tag(sync=True)
    view_request = traitlets.Dict().tag(sync=True)
    height = traitlets.Unicode("400px").tag(sync=True)

    def __init__(self, *, height: str = "400px", **kwargs):
        super().__init__(height=height, **kwargs)
