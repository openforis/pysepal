"""Right-panel section that exports the AOI and the processed outputs."""

import solara
from component.message import msg
from component.scripts import export_sources

from pysepal.solara.components.export import ExportLauncher


@solara.component
def ExportPanel(aoi_data, outputs, gee_interface, drive_interface):
    """Export the selected AOI and any processed outputs.

    The interfaces are threaded in rather than looked up here. Both
    ``get_current_gee_interface`` and ``get_current_drive_interface`` raise once
    the SessionManager is live but the current render has no session, and this
    panel is rendered as a child of MapApp's right panel -- a separate render
    root from the ``@with_sepal_sessions`` page that establishes the session.
    Resolving them once at the top of :func:`MapAppDemo` keeps the lookup where
    the session is known to exist.
    """
    ExportLauncher(
        sources=export_sources(aoi_data.value, outputs.value),
        dialog_title=msg("export.dialog_title"),
        default_target="gee",
        button_text=True,
        block=True,
        gee_interface=gee_interface,
        drive_interface=drive_interface,
    )
