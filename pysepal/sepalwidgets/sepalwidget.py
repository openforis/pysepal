"""Custom sepalwidgets to add extra members to normal ``IpyvuetfiWidget``.

Gather the customized ``ipyvuetifyWidgets`` used toadd extra members to the existing one.
All the content of this modules is included in the parent ``pysepal.sepalwidgets`` package. So it can be imported directly from there.

Example:
    .. jupyter-execute::

        from pysepal import sepalwidgets as sw

        sw.Tooltip(widget=sw.Btn(), tooltip="tooltip")
"""

from pathlib import Path

import ipyvuetify as v
import traitlets as t
from ipywidgets import DOMWidget
from ipywidgets.widgets.widget import widget_serialization

from pysepal._sepal_widget import SepalWidget, Tooltip

__all__ = ["Dialog", "SepalWidget", "Tooltip"]


class Dialog(v.VuetifyTemplate, SepalWidget):
    """Custom Dialog that triggers a window resize event."""

    children = t.List(t.Union([t.Instance(DOMWidget), t.Unicode()])).tag(
        sync=True, **widget_serialization
    )

    template_file = t.Unicode(str(Path(__file__).parent / "vue/Dialog.vue")).tag(sync=True)
    show = t.Bool(False).tag(sync=True)
    max_width = t.Union([t.Unicode(), t.Float()], default_value=None, allow_none=True).tag(
        sync=True
    )
    min_width = t.Union([t.Unicode(), t.Float()], default_value=None, allow_none=True).tag(
        sync=True
    )
    persistent = t.Bool(False).tag(sync=True)
    retain_focus = t.Bool(False).tag(sync=True)

    def open_dialog(self, *_):
        """Open dialog."""
        self.show = True

    def close_dialog(self, *_):
        """Close dialog."""
        self.show = False
