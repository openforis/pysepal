"""ipecharts in the places a pysepal app actually mounts a chart.

ECharts lays its canvas out once and redraws only when something calls
``resize()``. ipecharts calls it on a window resize, on Lumino resize messages,
on ``after-attach``, and when ``style`` or the CSS classes change -- and its
debouncer skips the redraw while the element is under 10px, which is the state of
anything mounted inside a closed panel. None of that covers a container that
changes width on its own, which is what MapApp's right panel does.

So every context here shows the same data twice: once as ipecharts mounts it, and
once with the app passing on what it knows about the layout. Flip a panel, switch
a tab, drag the panel edge, and watch which of the two follows.

The UI lives in :func:`ChartAppDemo` so both runtimes share it -- ``Page`` is the
Solara entrypoint, ``ui.ipynb`` the Voila one. Voila puts the charts in a Lumino
layout, which is where ipecharts' resize messages come from, so it looks like it
should behave differently. Measured: it does not. Lumino sends those messages
when its own layout changes, not when CSS moves something inside one output, so
both runtimes get the same two cases wrong.

To run:

```bash
pysepal$ ./run_solara.sh demo_apps/solara_chart_app/app.py --port 8901
pysepal$ voila demo_apps/solara_chart_app/ui.ipynb --port 8902
```
"""

import itertools

import reacton.ipyvuetify as rv
import solara
from chart_messages import messages, msg
from chart_options import sample_series
from chart_widgets import (
    ChartPair,
    build_map_chart_card,
    build_widget_button,
    nudge_resize,
)

from pysepal import mapping as sm
from pysepal.mapping.fullscreen_control import FullScreenControl
from pysepal.mapping.menu_control import MenuControl
from pysepal.sepalwidgets.vue_app import MapApp
from pysepal.solara import (
    get_current_theme_state,
    setup_solara_server,
    setup_theme_colors,
)
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
    """The contexts a plain Solara page can hold, control case first."""
    wide = solara.use_reactive(False)
    panel = solara.use_reactive(None)
    panel_token = solara.use_reactive(0)
    tab = solara.use_reactive(0)
    tab_token = solara.use_reactive(0)

    def open_panel(index):
        panel.value = index
        panel_token.value += 1

    def switch_tab(index):
        tab.value = index
        tab_token.value += 1

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
            # No token: nothing here changes the box but the window, which
            # ipecharts already listens for. This is what working looks like.
            ChartPair(values, resize_token=0)

        with solara.Card(title=msg("contexts.width.title")):
            solara.Markdown(msg("contexts.width.description"))
            solara.Switch(label=msg("buttons.wide"), value=wide.value, on_value=wide.set)
            with solara.Column(style={"width": "100%" if wide.value else "50%"}):
                ChartPair(values, resize_token=int(wide.value), line=True)

        with solara.Card(title=msg("contexts.panel.title")):
            solara.Markdown(msg("contexts.panel.description"))
            rv.ExpansionPanels(
                v_model=panel.value,
                on_v_model=open_panel,
                accordion=True,
                children=[
                    rv.ExpansionPanel(
                        children=[
                            rv.ExpansionPanelHeader(children=[msg("contexts.panel.header")]),
                            rv.ExpansionPanelContent(
                                children=[ChartPair(values, resize_token=panel_token.value)]
                            ),
                        ]
                    )
                ],
            )

        with solara.Card(title=msg("contexts.tabs.title")):
            solara.Markdown(msg("contexts.tabs.description"))
            with solara.lab.Tabs(value=tab.value, on_value=switch_tab):
                with solara.lab.Tab(msg("contexts.tabs.first")):
                    solara.Markdown(msg("contexts.tabs.first_body"))
                with solara.lab.Tab(msg("contexts.tabs.second")):
                    ChartPair(values, resize_token=tab_token.value, line=True)


@solara.component
def MapContexts(values: list, on_back):
    """The MapApp shell: a panel that changes width, a dialog step, a map overlay."""
    theme_state = get_current_theme_state()
    token = solara.use_reactive(0)

    def build_scene():
        """Map, overlay chart, and the fullscreen button wired to redraw it."""
        sepal_map = sm.SepalMap(
            zoom=3,
            center=[0, 0],
            gee=False,
            fullscreen=True,
            fullscreen_control=True,
            theme_state=theme_state,
        )
        card, chart = build_map_chart_card(values, msg("contexts.map.card_title"), width="360px")
        sepal_map.add(
            MenuControl(
                "mdi-chart-bar",
                card,
                m=sepal_map,
                card_title=msg("contexts.map.card_title"),
                position="topright",
            )
        )
        # Fullscreen changes the map's box without touching the window, so the
        # overlay hears it from the button that caused it.
        ticks = itertools.count(1)
        for control in sepal_map.controls:
            if isinstance(control, FullScreenControl):
                control.w_btn.on_event("click", lambda *args: nudge_resize(chart, next(ticks)))
        return sepal_map, chart

    sepal_map, _map_chart = solara.use_memo(build_scene, [])

    back_button = solara.use_memo(
        lambda: build_widget_button(msg("buttons.back"), on_back), [msg("buttons.back")]
    )

    map_app = MapApp.element(
        app_title=msg("app.title"),
        app_icon="mdi-chart-box",
        main_map=[sepal_map],
        steps_data=[
            {
                "id": 1,
                "name": msg("contexts.dialog.title"),
                "icon": "mdi-window-maximize",
                "display": "dialog",
                "content": [ChartPair(values, resize_token=token.value)],
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
                "content": [ChartPair(values, resize_token=token.value), back_button],
                "description": msg("contexts.right_panel.description"),
            }
        ],
        right_panel_open=True,
        theme_state=theme_state,
        locales=messages.available_locales(),
        dialog_width=750,
    )

    def watch_layout():
        """MapApp syncs its own geometry, so the charts can be told from Python."""
        widget = solara.get_widget(map_app)
        if widget is None:
            return None

        traits = ["right_panel_open", "right_panel_width", "step_open"]

        def on_layout(change):
            token.value += 1

        widget.observe(on_layout, traits)
        return lambda: widget.unobserve(on_layout, traits)

    solara.use_effect(watch_layout, [])


@solara.component
def Page():
    """Solara entrypoint -- no session and no credentials, the data is synthetic."""
    ChartAppDemo()
