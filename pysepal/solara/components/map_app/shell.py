"""The native Solara MapApp shell: a full-screen map with a drawer of steps and a tool panel."""

import contextlib
from pathlib import Path
from typing import Callable, Iterable, Mapping, Optional, Sequence, Union

import reacton.ipyvue as ipyvue
import reacton.ipyvuetify as rv
import solara

from pysepal._vuetify import IPYVUETIFY_V3
from pysepal.message import msg
from pysepal.solara.theme import ThemeState, resolve_theme_state

from ._ui import as_children
from .bridges import ViewportBridge
from .drawer import Drawer, external_links
from .right_panel import RightPanel
from .step_dialog import StepDialog, clamp

CSS = Path(__file__).with_name("map_app.css")

NARROW_BREAKPOINT_PX = 960
"Below this window width the drawer is a rail and the panel docks at the bottom."

NARROW_PANEL_HEIGHT_VH = 45
"Height of the docked panel, in percent of the window height."

RAIL_WIDTH_PX = 60
DRAWER_WIDTH_PX = 320
DISPLAYS = ("step", "dialog")

_FIELD = {"color": "primary", "variant": "underlined"}
_CONTROL = {"color": "primary"}
V3_DEFAULTS = {
    **dict.fromkeys(
        ["VTextField", "VTextarea", "VSelect", "VAutocomplete", "VCombobox", "VFileInput"], _FIELD
    ),
    **dict.fromkeys(
        ["VCheckbox", "VCheckboxBtn", "VRadioGroup", "VRadio", "VSwitch", "VSlider"], _CONTROL
    ),
}
"""Vuetify 3 defaults for everything the shell holds, its dialogs and menus included.

Vuetify 3 fills fields and drops the primary accent of focused and selected
controls; these give an app the Vuetify 2 look it was designed with. A prop set
on a component still wins.
"""


def _defaults():
    """Return the context that gives the shell's content its Vuetify 3 defaults."""
    if IPYVUETIFY_V3:
        return rv.DefaultsProvider(defaults=V3_DEFAULTS)
    return contextlib.nullcontext()


def _map_widget(main_map):
    if isinstance(main_map, (list, tuple)):
        return main_map[0] if main_map else None
    return main_map


def _find(steps: Sequence[Mapping], step_id) -> Optional[Mapping]:
    if step_id is None:
        return None
    return next((step for step in steps if step.get("id") == step_id), None)


def _has_content(step: Optional[Mapping]) -> bool:
    return bool(step) and bool(as_children(step.get("content")))


def _can_auto_activate(step: Optional[Mapping]) -> bool:
    return (
        _has_content(step)
        and step.get("content_enabled") is not False
        and step.get("display") in DISPLAYS
    )


def _is_dialog(step: Optional[Mapping]) -> bool:
    return bool(step) and step.get("display") == "dialog"


def initial_step_id(steps, initial_step, current_step, has_map) -> Optional[int]:
    """Return the step a new shell opens on.

    ``current_step`` if it names a step, else ``initial_step`` if it can show,
    else -- only when there is no map to show -- the first step that can.
    """
    if _find(steps, current_step) is not None:
        return current_step
    if _can_auto_activate(_find(steps, initial_step)):
        return initial_step
    if not has_map:
        first = next((step for step in steps if _can_auto_activate(step)), None)
        return first.get("id") if first else None
    return None


def use_prop_change(value, apply: Callable) -> None:
    """Call ``apply(value)`` when the ``value`` prop changes, not on the first render.

    The shell owns its state and a parent may pass the same value on every
    render; only a change is an instruction.
    """
    first = solara.use_ref(True)

    def effect():
        if first.current:
            first.current = False
            return
        apply(value)

    solara.use_effect(effect, [value])


@solara.component
def MapContainer(map_widget, on_click: Callable[[], None]):
    """Render the map behind the shell."""
    container = rv.Html(
        tag="div",
        class_="map-background sepal-mapapp__map",
        attributes={"id": "map-container"},
        children=[map_widget],
    )
    ipyvue.use_event(container, "click", lambda *_: on_click())
    return container


@solara.component
def DrawerToggle(rail: bool, on_click: Callable[[], None]):
    """Render the tab that collapses or expands the drawer."""
    with rv.Html(tag="div", class_="sidebar-controls sepal-mapapp__drawer-toggle") as main:
        btn = rv.Btn(
            tile=True,
            color="primary",
            class_="control-btn mb-2",
            attributes={"title": msg("map_app.expand" if rail else "map_app.collapse")},
            children=[rv.Icon(children=["mdi-menu-right" if rail else "mdi-menu-left"])],
        )
    ipyvue.use_event(btn, "click", lambda *_: on_click())
    return main


@solara.component
def MapApp(
    app_title: str = "Map Application",
    app_icon: str = "mdi-earth",
    main_map=None,
    steps_data: Sequence[Mapping] = (),
    right_panel_config: Optional[Mapping] = None,
    right_panel_content: Sequence[Mapping] = (),
    right_panel_footer: Sequence = (),
    right_panel_open: bool = False,
    on_right_panel_open: Optional[Callable[[bool], None]] = None,
    initial_step: Optional[int] = None,
    current_step: Optional[int] = None,
    on_current_step: Optional[Callable[[Optional[int]], None]] = None,
    step_open: bool = False,
    on_step_open: Optional[Callable[[bool], None]] = None,
    is_pinned: bool = True,
    theme_state: Optional[ThemeState] = None,
    locales: Optional[Iterable[str]] = None,
    repo_url: str = "",
    docs_url: str = "",
    dialog_width: Union[int, str] = 800,
    dialog_fullscreen: bool = False,
):
    """Render a full-screen map application.

    The map fills the window. A drawer on the left lists the steps, the links
    and the theme and language controls; a panel on the right holds sections of
    tools. Below 960px the drawer is a rail and the panel docks at the bottom.

    It takes the keyword arguments of the legacy
    ``pysepal.sepalwidgets.vue_app.MapApp.element``, so moving an app means
    changing the import and dropping ``.element``.

    Args:
        app_title: Title at the top of the drawer.
        app_icon: MDI icon beside the title.
        main_map: The map widget, or a one-item list holding it. It gets the
            panels' insets (``viewport_inset_*``), the window size
            (``canvas_*_px``) and the theme (``bind_theme_state``) when it has them.
        steps_data: Drawer steps: ``id``, ``name``, ``icon``, ``display``
            (``"step"`` replaces the map, ``"dialog"`` opens a dialog, anything
            else only reports ``current_step``), ``content`` (an element, a
            widget or a list of them; a step without content only runs its
            ``right_panel_action``), ``content_enabled``, ``right_panel_action``
            (``"open"``, ``"close"`` or ``"toggle"``), ``actions`` (dialog
            footer buttons: ``label``, ``cancel``, ``close``, ``next``),
            ``width`` and ``height`` (px or ``"NN%"``, dialog steps).
        right_panel_config: ``title``, ``icon``, ``width``, ``description`` and
            ``toggle_icon`` of the right panel.
        right_panel_content: The panel sections: ``title``, ``icon``,
            ``description``, ``content`` and ``divider``. No section, no panel.
        right_panel_footer: Widgets or elements pinned below the sections.
        right_panel_open: Whether the panel starts open; a later change opens or
            closes it.
        on_right_panel_open: Called when the user opens or closes the panel.
        initial_step: The step to open on mount.
        current_step: The active step; a later change activates it (``None``
            shows the map).
        on_current_step: Called with the step the user activates (``None`` for
            the map).
        step_open: A later change to False closes the step dialog, to True
            reopens it.
        on_step_open: Called when a step opens or closes.
        is_pinned: Whether the drawer starts pinned open. An unpinned drawer
            starts as a rail and collapses on a click on the map.
        theme_state: The theme state the toggle and the map follow; defaults to
            the current scope's.
        locales: The locale codes the language selector offers.
        repo_url: Target of the Source Code and Report Bug links; empty hides both.
        docs_url: Target of the Documentation link; empty hides it.
        dialog_width: Default width of dialog steps.
        dialog_fullscreen: Show dialog steps full screen.
    """
    state = resolve_theme_state(theme_state)
    map_widget = _map_widget(main_map)
    steps = list(steps_data)
    has_map = map_widget is not None
    has_panel = bool(right_panel_content)

    window, set_window = solara.use_state({"w": 0, "h": 0})
    width, height = int(window.get("w", 0)), int(window.get("h", 0))
    narrow = 0 < width < NARROW_BREAKPOINT_PX

    pinned, set_pinned = solara.use_state(is_pinned)
    rail, set_rail = solara.use_state(not is_pinned)
    active_id, set_active_id = solara.use_state(
        initial_step_id(steps, initial_step, current_step, has_map)
    )
    dialog_open, set_dialog_open = solara.use_state(_is_dialog(_find(steps, active_id)))
    panel_open, set_panel_state = solara.use_state(bool(right_panel_open))
    active_step = _find(steps, active_id)

    def report(step_id: Optional[int], is_open: bool):
        if on_current_step is not None:
            on_current_step(step_id)
        if on_step_open is not None:
            on_step_open(is_open)

    def set_panel_open(value: bool):
        set_panel_state(value)
        if on_right_panel_open is not None:
            on_right_panel_open(value)

    def activate(step: Mapping):
        if dialog_open:
            return
        action = step.get("right_panel_action")
        if action in ("open", "close", "toggle"):
            set_panel_open({"open": True, "close": False, "toggle": not panel_open}[action])
        if not _has_content(step):
            return
        set_active_id(step.get("id"))
        set_dialog_open(_is_dialog(step))
        report(step.get("id"), True)

    def show_map():
        if dialog_open:
            return
        set_active_id(None)
        set_dialog_open(False)
        report(None, False)

    def close_dialog():
        set_dialog_open(False)
        set_active_id(None)
        report(None, False)

    def on_action(action: Mapping):
        if action.get("close"):
            close_dialog()
        target = action.get("next")
        if target is not None:
            set_active_id(target)
            set_dialog_open(_is_dialog(_find(steps, target)))
            report(target, True)

    def apply_current_step(value):
        if value is not None and value != active_id:
            step = _find(steps, value)
            if step is not None:
                set_active_id(value)
                if _is_dialog(step):
                    set_dialog_open(True)
        elif value is None and active_id is not None:
            set_active_id(None)
            set_dialog_open(False)

    def apply_step_open(value):
        if not value and dialog_open:
            set_dialog_open(False)
        elif value and _is_dialog(active_step):
            set_dialog_open(True)

    use_prop_change(current_step, apply_current_step)
    use_prop_change(step_open, apply_step_open)
    use_prop_change(bool(right_panel_open), set_panel_state)

    def follow_window():
        if narrow:
            set_rail(True)
        elif pinned:
            set_rail(False)

    solara.use_effect(follow_window, [narrow])

    drawer_px = RAIL_WIDTH_PX if rail else DRAWER_WIDTH_PX
    panel_px = int((right_panel_config or {}).get("width") or 300)
    right_px = panel_px if has_panel and panel_open and not narrow else 0
    narrow_bottom = narrow and has_panel and panel_open
    if narrow_bottom:
        bottom_reserved = f"{NARROW_PANEL_HEIGHT_VH}vh"
    elif narrow and has_panel:
        bottom_reserved = "48px"
    else:
        bottom_reserved = "0px"

    css_vars = {
        "--sepal-right-panel-width": f"{right_px}px",
        "--sepal-right-panel-open": "1" if right_px else "0",
        "--sepal-notification-right-offset": f"{right_px}px",
        "--sepal-drawer-width": f"{drawer_px}px",
        "--sepal-bottom-reserved": bottom_reserved,
    }

    def push_insets():
        if map_widget is None or not hasattr(map_widget, "viewport_inset_left"):
            return
        map_widget.viewport_inset_left = drawer_px
        map_widget.viewport_inset_right = right_px
        if hasattr(map_widget, "viewport_inset_bottom"):
            docked = narrow and has_panel
            map_widget.viewport_inset_bottom = (
                int(height * NARROW_PANEL_HEIGHT_VH / 100) if docked else 0
            )
        if width > 0 and hasattr(map_widget, "canvas_width_px"):
            map_widget.canvas_width_px = width
        if height > 0 and hasattr(map_widget, "canvas_height_px"):
            map_widget.canvas_height_px = height

    solara.use_effect(
        push_insets, [id(map_widget), drawer_px, right_px, narrow, has_panel, width, height]
    )

    def bind_theme():
        if map_widget is not None and hasattr(map_widget, "bind_theme_state"):
            map_widget.bind_theme_state(state)

    solara.use_effect(bind_theme, [id(map_widget), id(state)])

    def collapse_if_unpinned():
        if not pinned and not rail:
            set_rail(True)

    classes = ["sepal-mapapp"]
    if rail:
        classes.append("sepal-mapapp--rail")
    if narrow:
        classes.append("sepal-mapapp--narrow")
    if narrow_bottom:
        classes.append("sepal-mapapp--narrow-bottom")
    local_vars = (
        f"--sepal-mapapp-drawer: {drawer_px}px; --sepal-mapapp-right: {right_px}px; "
        f"--sepal-mapapp-bottom: {bottom_reserved}"
    )

    step_steps = [s for s in steps if s.get("display") == "step" and _has_content(s)]
    dialog_steps = [s for s in steps if _is_dialog(s) and _has_content(s)]
    showing_step = active_step is not None and active_step.get("display") == "step"
    dialog_step = active_step if _is_dialog(active_step) else None

    with rv.Html(tag="div", class_=" ".join(classes), style_=local_vars) as main:
        solara.Style(CSS)
        with _defaults():
            ViewportBridge(
                css_vars=css_vars,
                body_class="sepal-modal-open" if dialog_open else "",
                event_window_size=set_window,
            )

            if has_map:
                MapContainer(map_widget, on_click=collapse_if_unpinned)

            if step_steps:
                with rv.Sheet(
                    tile=True,
                    elevation=0,
                    class_="step-content-container sepal-mapapp__step",
                    style_="" if showing_step else "display: none",
                ):
                    for step in step_steps:
                        rv.Html(
                            tag="div",
                            style_="" if step.get("id") == active_id else "display: none",
                            children=as_children(step.get("content")),
                        ).key(f"step-{step.get('id')}")

            Drawer(
                app_title=app_title,
                app_icon=app_icon,
                has_map=has_map,
                steps=steps,
                active_step_id=active_id,
                rail=rail,
                pinned=pinned,
                disabled=dialog_open,
                links=external_links(repo_url, docs_url),
                theme_state=state,
                locales=locales,
                on_map=show_map,
                on_step=activate,
                on_pin=lambda: set_pinned(not pinned),
            )
            DrawerToggle(rail=rail, on_click=lambda: set_rail(not rail))

            if has_panel:
                RightPanel(
                    config=right_panel_config,
                    sections=right_panel_content,
                    footer=right_panel_footer,
                    open=panel_open,
                    on_open=set_panel_open,
                    narrow=narrow,
                )

            if dialog_steps:
                target_width = (dialog_step or {}).get("width") or dialog_width
                StepDialog(
                    open=dialog_open and dialog_step is not None,
                    step=dialog_step,
                    dialog_steps=dialog_steps,
                    width=clamp(target_width, width, width - drawer_px - 40, 800),
                    height=clamp((dialog_step or {}).get("height"), height, height - 80, None),
                    fullscreen=dialog_fullscreen,
                    on_close=close_dialog,
                    on_action=on_action,
                )

    return main
