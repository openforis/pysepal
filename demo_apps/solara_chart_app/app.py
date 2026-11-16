"""ipecharts in the places a pysepal app actually mounts a chart.

ECharts lays its canvas out when it draws. Since ipecharts 1.4.2 the chart also
watches its element with a ``ResizeObserver`` and draws again when the element
changes size or becomes visible, so none of these contexts carries resize code.
Change a layout and check that the chart follows: a card that changes width, a
collapsed panel, an unopened tab, MapApp's right panel, a dialog step, and a menu
on the map.

The UI lives in :func:`ChartAppDemo` so both runtimes share it -- ``Page`` is the
Solara entrypoint, ``ui.ipynb`` the Voila one.

To run:

```bash
pysepal$ ./run_solara.sh demo_apps/solara_chart_app/app.py --port 8901
pysepal$ voila demo_apps/solara_chart_app/ui.ipynb --port 8902
```
"""

import reacton.ipyvuetify as rv
import solara
from chart_messages import messages, msg
from chart_options import sample_series
from chart_widgets import ContextChart, build_map_chart_card

from pysepal import mapping as sm
from pysepal.mapping.menu_control import MenuControl
from pysepal.solara import (
    get_current_theme_state,
    setup_solara_server,
    setup_theme_colors,
)
from pysepal.solara.components.map_app import MapApp
from pysepal.solara.notifications import NotificationProvider, use_notifications

setup_solara_server(extra_asset_locations=[])


@solara.component
def ChartAppDemo():
    """Mount the notification bus, then the contexts that publish to it.

    The bus exists once the provider element has rendered, which is after this
    body has finished -- so the hook has to run in a child, not alongside it.
    """
    NotificationProvider()
    ChartLab()


@solara.component
def ChartLab():
    """One data set, two layouts: a plain page, and the MapApp shell."""
    setup_theme_colors()
    notifications = use_notifications()

    initial = solara.use_memo(sample_series, [])
    values = solara.use_reactive(initial)
    in_map = solara.use_reactive(False)

    def regenerate():
        values.value = sample_series()
        notifications.info(msg("toasts.regenerated"))

    if in_map.value:
        MapContexts(values.value, on_back=lambda: in_map.set(False))
    else:
        PageContexts(
            values.value,
            on_map=lambda: in_map.set(True),
            on_regenerate=regenerate,
        )


@solara.component
def PageContexts(values: list, on_map, on_regenerate):
    """The contexts a plain Solara page can hold."""
    wide = solara.use_reactive(False)
    panel = solara.use_reactive(None)
    tab = solara.use_reactive(0)

    # The gallery hands a demo a 100vh box and no chrome, so this page scrolls itself.
    with solara.Column(
        style={
            "padding": "16px",
            "max-width": "1100px",
            "margin": "0 auto",
            "height": "100%",
            "overflow-y": "auto",
        },
        gap="16px",
    ):
        solara.Markdown(f"## {msg('app.title')}\n\n{msg('page.intro')}")

        with solara.Row():
            solara.Button(msg("buttons.regenerate"), on_click=on_regenerate, outlined=True)
            solara.Button(msg("buttons.open_map"), on_click=on_map, color="primary")

        with solara.Card(title=msg("contexts.column.title")):
            solara.Markdown(msg("contexts.column.description"))
            ContextChart(values)

        with solara.Card(title=msg("contexts.width.title")):
            solara.Markdown(msg("contexts.width.description"))
            solara.Switch(label=msg("buttons.wide"), value=wide.value, on_value=wide.set)
            with solara.Column(style={"width": "100%" if wide.value else "50%"}):
                ContextChart(values, line=True)

        with solara.Card(title=msg("contexts.panel.title")):
            solara.Markdown(msg("contexts.panel.description"))
            rv.ExpansionPanels(
                v_model=panel.value,
                on_v_model=panel.set,
                variant="accordion",
                children=[
                    rv.ExpansionPanel(
                        children=[
                            rv.ExpansionPanelTitle(children=[msg("contexts.panel.header")]),
                            rv.ExpansionPanelText(children=[ContextChart(values)]),
                        ]
                    )
                ],
            )

        with solara.Card(title=msg("contexts.tabs.title")):
            solara.Markdown(msg("contexts.tabs.description"))
            with solara.lab.Tabs(value=tab.value, on_value=tab.set):
                with solara.lab.Tab(msg("contexts.tabs.first")):
                    solara.Markdown(msg("contexts.tabs.first_body"))
                with solara.lab.Tab(msg("contexts.tabs.second")):
                    ContextChart(values, line=True)


@solara.component
def MapContexts(values: list, on_back):
    """The MapApp shell: a right panel, a dialog step, a menu on the map."""
    theme_state = get_current_theme_state()

    def build_map():
        sepal_map = sm.SepalMap(
            zoom=3,
            center=[0, 0],
            gee=False,
            fullscreen=True,
            fullscreen_control=True,
            theme_state=theme_state,
        )
        sepal_map.add(
            MenuControl(
                "mdi-chart-bar",
                build_map_chart_card(values, width="360px"),
                m=sepal_map,
                card_title=msg("contexts.map.card_title"),
                position="topright",
            )
        )
        return sepal_map

    sepal_map = solara.use_memo(build_map, [])

    MapApp(
        app_title=msg("app.title"),
        app_icon="mdi-chart-box",
        main_map=[sepal_map],
        steps_data=[
            {
                "id": 1,
                "name": msg("contexts.dialog.title"),
                "icon": "mdi-window-maximize",
                "display": "dialog",
                "content": [ContextChart(values)],
            }
        ],
        right_panel_config={
            "title": msg("panel.title"),
            "icon": "mdi-chart-bar",
            "width": 400,
            "description": msg("panel.description"),
        },
        right_panel_content=[
            {
                "title": msg("contexts.right_panel.title"),
                "icon": "mdi-chart-bar",
                "content": [
                    ContextChart(values),
                    solara.Button(
                        msg("buttons.back"),
                        on_click=on_back,
                        block=True,
                        classes=["mt-2"],
                        size="small",
                    ),
                ],
                "description": msg("contexts.right_panel.description"),
            }
        ],
        right_panel_open=True,
        theme_state=theme_state,
        locales=messages.available_locales(),
        dialog_width=750,
    )


@solara.component
def Page():
    """Solara entrypoint -- no session and no credentials, the data is synthetic."""
    ChartAppDemo()
