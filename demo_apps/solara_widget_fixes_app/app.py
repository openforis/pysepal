"""Four widget fixes to try by hand: three right-panel sections and a dialog step.

- #1092: MapApp shows the Documentation link only when it gets a ``docs_url``.
- #1093: ``sw.Markdown.element(mkd_str=...)`` follows its text, with no key.
- #1094: a ``solara.Markdown`` inside an ``rv.Alert`` takes the alert's colour.
- #1103: ``ExportLauncher`` calls ``resolve`` once per selection, not on every render.

The export section needs Earth Engine, so ``Page`` opens a SEPAL session. When no
session or no Earth Engine credentials are available, that section says so and
the other three still work.

The UI lives in :func:`WidgetFixesDemo` so the same code serves both runtimes --
``Page`` adds the SEPAL session for Solara and ``ui.ipynb`` is a thin Voila one.

To run (the export section needs SEPAL credentials in a ``.env`` at the repo root):

```bash
pysepal$ ./run_solara.sh demo_apps/solara_widget_fixes_app/app.py --port 8901
```
"""

from pathlib import Path

import ee
import ipyvuetify as v
import reacton.ipyvuetify as rv
import solara

import pysepal.sepalwidgets as sw
from pysepal import mapping as sm
from pysepal.i18n import catalog
from pysepal.scripts.gee import init_ee
from pysepal.sepalwidgets.vue_app import MapApp
from pysepal.solara import (
    get_current_drive_interface,
    get_current_gee_interface,
    get_current_theme_state,
    setup_sessions,
    setup_solara_server,
    setup_theme_colors,
    with_sepal_sessions,
)
from pysepal.solara.components.export import (
    ExportLauncher,
    ExportSource,
    ResolvedExport,
)
from pysepal.solara.notifications import NotificationProvider

setup_solara_server(extra_asset_locations=[])


@solara.lab.on_kernel_start
def on_kernel_start():
    """Set up sessions management."""
    return setup_sessions()


#: Flat catalogue, no ``component/`` package: ``gallery.py`` puts every demo
#: directory on ``sys.path``, and the map app owns that name.
MESSAGE_DIR = Path(__file__).parent / "message"
messages = catalog(MESSAGE_DIR)
msg = messages.msg

DOCS_URL = "https://pysepal.readthedocs.io/en/latest/"
REPO_URL = "https://github.com/openforis/pysepal"

MARKDOWN_TEXTS = ("markdown.texts.first", "markdown.texts.second", "markdown.texts.third")

ALERT_TYPES = ("success", "info", "warning", "error")
ALERT_VARIANTS = {"filled": {}, "tinted": {"text": True}, "outlined": {"outlined": True}}

#: Kilimanjaro summit, as (lon, lat).
SUMMIT = (37.3556, -3.0674)
BUFFERS_KM = (2, 5, 10)


def open_earth_engine(session_error: str = ""):
    """Return ``(gee_interface, drive_interface, error)``.

    The interfaces are None when Earth Engine is not available; ``error`` then
    says why, or is None when there are simply no credentials on this machine.
    """
    if session_error:
        return None, None, session_error
    try:
        gee_interface = get_current_gee_interface()
        drive_interface = get_current_drive_interface()
        # Building an ee graph in resolve needs the global ee, as SepalMap(gee=True) does.
        init_ee()
    except Exception as error:
        return None, None, str(error) or type(error).__name__
    if not ee.data.is_initialized():
        return None, None, None
    return gee_interface, drive_interface, None


class ResolveLog:
    """Count the ``resolve`` calls and show them in a plain widget.

    ``resolve`` runs while the export hook renders, so it must not set Solara
    state. A widget trait is not Solara state: writing it re-renders nothing.
    """

    def __init__(self):
        """Start with no call recorded."""
        self.count = 0
        self.entries = []
        self.widget = v.Html(tag="div", class_="text-caption mt-2")

    def record(self, source_id: str, buffer_km: int) -> None:
        """Count one call of ``resolve`` and show it."""
        self.count += 1
        self.entries.insert(0, (self.count, source_id, buffer_km))
        del self.entries[6:]
        self.show()

    def show(self) -> None:
        """Write the log in the current language."""
        if not self.count:
            lines = [msg("export.log.empty")]
        else:
            lines = [msg("export.log.count", count=self.count)] + [
                msg(
                    "export.log.entry",
                    n=str(n),
                    source=msg(f"export.sources.{source_id}.label"),
                    km=str(km),
                )
                for n, source_id, km in self.entries
            ]
        self.widget.children = [v.Html(tag="div", children=[line]) for line in lines]


def terrain_sources(buffer_km: int, log: ResolveLog) -> list:
    """Two image sources clipped to a buffer around the summit.

    Rebuilt on every render on purpose: each resolve is a new function with the
    same code and the same captured ``buffer_km``, so the hook keeps its result.
    """

    def resolve(source_id: str) -> ResolvedExport:
        log.record(source_id, buffer_km)
        region = ee.Geometry.Point(SUMMIT).buffer(buffer_km * 1000)
        dem = ee.Image("USGS/SRTMGL1_003").select("elevation")
        image = dem if source_id == "elevation" else ee.Terrain.slope(dem)
        return ResolvedExport(
            ee_object=image.clip(region),
            default_name=f"kilimanjaro_{source_id}_{buffer_km}km",
            region=region,
            default_scale=30,
            drive_folder="pysepal_exports",
            sepal_folder="exports",
        )

    return [
        ExportSource(
            id=source_id,
            label=msg(f"export.sources.{source_id}.label"),
            kind="image",
            description=msg(f"export.sources.{source_id}.description"),
            resolve=lambda source_id=source_id: resolve(source_id),
        )
        for source_id in ("elevation", "slope")
    ]


@solara.component
def AlertColours():
    """Markdown in every alert type and variant, and once outside any alert."""
    with rv.Html(tag="div"):
        rv.Html(tag="p", class_="text-body-2", children=[msg("alerts.description")])
        for variant, style in ALERT_VARIANTS.items():
            for type_ in ALERT_TYPES:
                with rv.Alert(type=type_, dense=True, class_="mb-1", **style):
                    solara.Markdown(
                        msg(
                            "alerts.sample",
                            type=msg(f"alerts.types.{type_}"),
                            variant=msg(f"alerts.variants.{variant}"),
                        )
                    )
        solara.Markdown(msg("alerts.outside"))


@solara.component
def WidgetFixesDemo(gee_error: str = ""):
    """Mount the notification bus, then the app that publishes to it.

    The bus exists only once the provider element has rendered, so the export
    dialog that publishes to it lives one level down, in :func:`_FixesShell`.
    """
    NotificationProvider()
    _FixesShell(gee_error=gee_error)


@solara.component
def _FixesShell(gee_error: str = ""):
    """The MapApp shell: one section or step per fix."""
    setup_theme_colors()
    theme_state = get_current_theme_state()
    gee_interface, drive_interface, ee_error = solara.use_memo(
        lambda: open_earth_engine(gee_error), [gee_error]
    )

    show_docs = solara.use_reactive(True)
    text_index = solara.use_reactive(0)
    renders = solara.use_reactive(0)
    buffer_km = solara.use_reactive(BUFFERS_KM[1])

    log = solara.use_memo(ResolveLog, [])
    log.show()

    sepal_map = solara.use_memo(
        lambda: sm.SepalMap(
            zoom=9,
            center=[SUMMIT[1], SUMMIT[0]],
            gee=False,
            fullscreen=True,
            theme_state=theme_state,
        ),
        [],
    )

    if gee_interface is None:
        export_content = [
            rv.Alert(
                type="warning",
                text=True,
                dense=True,
                children=[msg("export.no_gee", reason=ee_error or msg("export.no_credentials"))],
            )
        ]
    else:
        export_content = [
            rv.Html(tag="div", class_="text-caption", children=[msg("export.buffer")]),
            solara.ToggleButtonsSingle(value=buffer_km, values=list(BUFFERS_KM), dense=True),
            solara.Button(
                label=msg("export.rerender", renders=str(renders.value)),
                on_click=lambda: renders.set(renders.value + 1),
                icon_name="mdi-refresh",
                outlined=True,
                small=True,
                block=True,
                classes=["my-2"],
            ),
            ExportLauncher(
                sources=terrain_sources(buffer_km.value, log),
                label=msg("export.launcher"),
                dialog_title=msg("export.dialog_title"),
                default_target="gee",
                button_text=True,
                block=True,
                gee_interface=gee_interface,
                drive_interface=drive_interface,
            ),
            log.widget,
        ]

    MapApp.element(
        app_title=msg("app.title"),
        app_icon="mdi-wrench-check-outline",
        main_map=[sepal_map],
        # A dialog step, not a right-panel section: the right panel makes every
        # v-sheet transparent, which hides the background of a filled alert.
        steps_data=[
            {
                "id": 1,
                "name": msg("alerts.title"),
                "icon": "mdi-palette-outline",
                "display": "dialog",
                "content": [AlertColours()],
                "actions": [{"label": msg("alerts.close"), "close": True}],
            }
        ],
        repo_url=REPO_URL,
        docs_url=DOCS_URL if show_docs.value else "",
        right_panel_config={
            "title": msg("panel.title"),
            "icon": "mdi-wrench-check-outline",
            "width": 420,
            "description": msg("panel.description"),
        },
        right_panel_content=[
            {
                "title": msg("docs.title"),
                "icon": "mdi-book-open-page-variant",
                "content": [
                    rv.Switch(
                        label=msg("docs.switch"),
                        v_model=show_docs.value,
                        on_v_model=show_docs.set,
                        dense=True,
                        hint=(
                            msg("docs.hint_on", url=DOCS_URL)
                            if show_docs.value
                            else msg("docs.hint_off")
                        ),
                        persistent_hint=True,
                    )
                ],
                "description": msg("docs.description"),
            },
            {
                "title": msg("markdown.title"),
                "icon": "mdi-language-markdown-outline",
                "content": [
                    sw.Markdown.element(mkd_str=msg(MARKDOWN_TEXTS[text_index.value])),
                    solara.Button(
                        label=msg("markdown.next"),
                        on_click=lambda: text_index.set(
                            (text_index.value + 1) % len(MARKDOWN_TEXTS)
                        ),
                        icon_name="mdi-swap-horizontal",
                        outlined=True,
                        small=True,
                        block=True,
                    ),
                ],
                "description": msg("markdown.description"),
            },
            {
                "title": msg("export.title"),
                "icon": "mdi-export-variant",
                "content": export_content,
                "description": msg("export.description"),
            },
        ],
        right_panel_open=True,
        theme_state=theme_state,
        locales=messages.available_locales(),
        dialog_width=750,
    )


def _without_session(error: Exception) -> None:
    """Render the demo without Earth Engine when the session cannot open."""
    WidgetFixesDemo(gee_error=str(error) or type(error).__name__)


@solara.component
@with_sepal_sessions(module_name="solara_widget_fixes_app", error_handler=_without_session)
def Page():
    """Solara entrypoint: opens the SEPAL session that the export section uses."""
    WidgetFixesDemo()
