"""The native Solara MapApp shell: a full-screen map with a drawer of steps and a tool panel."""

from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence, Union

import reacton.ipyvuetify as rv
import solara

from pysepal.message import msg
from pysepal.solara.components.map_view import MapView
from pysepal.solara.theme import ThemeState, resolve_theme_state

from ._ui import Slot, as_children, step_keys
from .bridges import ViewportBridge
from .drawer import Belt, Drawer, external_links
from .right_panel import RightPanel, panel_width
from .step_dialog import StepDialog, clamp

CSS = Path(__file__).with_name("map_app.css")

NARROW_BREAKPOINT_PX = 960
"Below this window width the drawer is a bar across the top and the panel docks at the bottom."

NARROW_PANEL_HEIGHT_VH = 45
"Height of the docked panel, in percent of the window height."

RAIL_WIDTH_PX = 60
BELT_HEIGHT_PX = 48
DRAWER_WIDTH_PX = 320
DISPLAYS = ("step", "dialog")

_FIELD = {"color": "primary", "variant": "underlined"}
_CONTROL = {"color": "primary"}
DEFAULTS = {
    **dict.fromkeys(
        ["VTextField", "VTextarea", "VSelect", "VAutocomplete", "VCombobox", "VFileInput"], _FIELD
    ),
    **dict.fromkeys(
        ["VCheckbox", "VCheckboxBtn", "VRadioGroup", "VRadio", "VSwitch", "VSlider"], _CONTROL
    ),
}
"""Vuetify defaults for everything the shell holds, its dialogs and menus included.

They give the shell's content pysepal's look: underlined fields, and the primary
accent on focused and selected controls. A prop set on a component still wins.
"""


def _map_widget(main_map):
    if isinstance(main_map, (list, tuple)):
        return main_map[0] if main_map else None
    return main_map


def _index(steps: Sequence[Mapping], step_id) -> Optional[int]:
    if step_id is None:
        return None
    return next((i for i, step in enumerate(steps) if step.get("id") == step_id), None)


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


def initial_step_index(steps, initial_step, current_step, has_map) -> Optional[int]:
    """Return the index of the step a new shell opens on.

    ``current_step`` if it names a step with content, else ``initial_step`` if
    it can show, else -- only when there is no map to show -- the first step
    that can.
    """
    current = _index(steps, current_step)
    if current is not None and _has_content(steps[current]):
        return current
    initial = _index(steps, initial_step)
    if initial is not None and _can_auto_activate(steps[initial]):
        return initial
    if not has_map:
        return next((i for i, step in enumerate(steps) if _can_auto_activate(step)), None)
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


@solara.component_vue("MapFrame.vue")
def MapFrame(
    collapsible: bool,
    event_collapse: Optional[Callable[[Any], None]] = None,
    children: list = [],
):
    """Hold the map, and call ``event_collapse`` on a click on it while ``collapsible``.

    The browser checks ``collapsible``, so a click the drawer does not need, such as
    each vertex of a drawing, sends nothing to the kernel.
    """


@solara.component
def MapContainer(
    map_widget,
    collapsible: bool,
    on_collapse: Callable[[], None],
    overlays: Optional[Mapping] = None,
):
    """Render the map behind the shell, in a ``MapView`` when it has a layer store."""
    shown = (
        MapView(map_widget, overlays=overlays) if hasattr(map_widget, "layer_store") else map_widget
    )
    return MapFrame(
        collapsible=collapsible, event_collapse=lambda _: on_collapse(), children=[shown]
    )


@solara.component
def DrawerToggle(rail: bool, on_click: Callable[[], None]):
    """Render the tab that collapses or expands the drawer."""
    with rv.Html(tag="div", class_="sidebar-controls sepal-mapapp__drawer-toggle") as main:
        solara.Button(
            tile=True,
            color="primary",
            classes=["control-btn"],
            attributes={"title": msg("map_app.expand" if rail else "map_app.collapse")},
            children=[rv.Icon(children=["mdi-chevron-right" if rail else "mdi-chevron-left"])],
            on_click=on_click,
        )
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
    map_overlays: Optional[Mapping] = None,
):
    """Render a full-screen map application.

    The map fills the window. A drawer on the left lists the steps, the links
    and the theme and language controls; a panel on the right holds sections of
    tools. Below 960px the drawer is a bar across the top, the panel docks at
    the bottom and the task pill hides.

    It takes the keyword arguments of the legacy
    ``pysepal.sepalwidgets.vue_app.MapApp.element``, so moving an app means
    changing the import and dropping ``.element``.

    Args:
        app_title: Title at the top of the drawer.
        app_icon: MDI icon beside the title.
        main_map: The map widget, or a one-item list holding it. It gets the
            panels' insets (``set_insets``) and the theme (``bind_theme_state``)
            when it has them.
        steps_data: Drawer steps: ``id`` (reported through ``on_current_step``;
            give each step its own), ``name``, ``icon``, ``display``
            (``"step"`` replaces the map, ``"dialog"`` opens a dialog, anything
            else only reports ``current_step``), ``content`` (an element, a
            widget or a list of them; a step without content only runs its
            ``right_panel_action``), ``content_enabled``, ``right_panel_action``
            (``"open"``, ``"close"`` or ``"toggle"``), ``actions`` (dialog
            footer buttons: ``label``, ``cancel``, ``close``, ``next``; a
            ``next`` step without content closes the dialog), ``width`` and
            ``height`` (dialog steps: px as a number, ``"600"`` or ``"600px"``,
            or ``"NN%"`` of the window; a size that does not read falls back to
            ``dialog_width``).
        right_panel_config: ``title``, ``icon``, ``width`` (px as a number,
            ``"300"`` or ``"300px"``), ``description`` and ``toggle_icon`` of the
            right panel.
        right_panel_content: The panel sections: ``title``, ``icon``,
            ``description``, ``content`` and ``divider``. No section, no panel.
        right_panel_footer: Widgets or elements pinned below the sections.
        right_panel_open: Whether the panel starts open; a later change opens or
            closes it.
        on_right_panel_open: Called when the user opens or closes the panel.
        initial_step: The step to open on mount.
        current_step: The active step; a later change activates it, unless it
            has no content (``None`` shows the map).
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
        dialog_width: Default width of dialog steps, in the forms of a step's
            ``width``; 800 when it does not read.
        dialog_fullscreen: Show dialog steps full screen.
        map_overlays: Elements to stack over the map, by corner (``"top-left"``,
            ``"top-right"``, ``"bottom-left"``, ``"bottom-right"``). Used when the map has a
            ``layer_store``.
    """
    state = resolve_theme_state(theme_state)
    map_widget = _map_widget(main_map)
    steps = list(steps_data)
    has_map = map_widget is not None
    has_panel = bool(right_panel_content)

    window, set_window = solara.use_state({"w": 0, "h": 0})
    width, height = int(window.get("w", 0)), int(window.get("h", 0))
    narrow = 0 < width < NARROW_BREAKPOINT_PX

    # The shell tracks the active step by key, not by id: ids may repeat or be
    # missing.
    keys = step_keys(steps)
    by_key = dict(zip(keys, steps))

    def key_of(step_id) -> Optional[str]:
        index = _index(steps, step_id)
        return None if index is None else keys[index]

    pinned, set_pinned = solara.use_state(is_pinned)
    rail, set_rail = solara.use_state(not is_pinned)
    start = initial_step_index(steps, initial_step, current_step, has_map)
    active_key, set_active_key = solara.use_state(None if start is None else keys[start])
    dialog_open, set_dialog_open = solara.use_state(_is_dialog(by_key.get(active_key)))
    panel_open, set_panel_state = solara.use_state(bool(right_panel_open))
    active_step = by_key.get(active_key)
    dialog_step = active_step if _is_dialog(active_step) else None
    # The drawer locks only while a dialog is on screen: a dialog step whose
    # content went away renders no dialog the user could close.
    modal = dialog_open and _has_content(dialog_step)

    def report(step_id: Optional[int], is_open: bool):
        if on_current_step is not None:
            on_current_step(step_id)
        if on_step_open is not None:
            on_step_open(is_open)

    def set_panel_open(value: bool):
        set_panel_state(value)
        if on_right_panel_open is not None:
            on_right_panel_open(value)

    def go_to(key: str):
        set_active_key(key)
        set_dialog_open(_is_dialog(by_key[key]))

    def activate(index: int):
        if modal:
            return
        step = steps[index]
        action = step.get("right_panel_action")
        if action in ("open", "close", "toggle"):
            set_panel_open({"open": True, "close": False, "toggle": not panel_open}[action])
        if not _has_content(step):
            return
        go_to(keys[index])
        report(step.get("id"), True)

    def show_map():
        if modal:
            return
        set_active_key(None)
        set_dialog_open(False)
        report(None, False)

    def close_dialog():
        set_dialog_open(False)
        set_active_key(None)
        report(None, False)

    def on_action(action: Mapping):
        target = key_of(action.get("next"))
        if target is not None and _has_content(by_key[target]):
            go_to(target)
            report(action["next"], True)
        elif action.get("close") or action.get("next") is not None:
            close_dialog()

    def apply_current_step(value):
        if value is None:
            # A step without an id reports None when the user opens it; the
            # parent echoing that back must not close it.
            if active_step is None or active_step.get("id") is not None:
                set_active_key(None)
                set_dialog_open(False)
        elif value != (active_step or {}).get("id"):
            key = key_of(value)
            if key is not None and _has_content(by_key[key]):
                go_to(key)

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

    if narrow:
        drawer_px = 0
    else:
        drawer_px = RAIL_WIDTH_PX if rail else DRAWER_WIDTH_PX
    top_px = BELT_HEIGHT_PX if narrow else 0
    panel_px = panel_width(right_panel_config)
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
        "--sepal-notification-pill-display": "none" if narrow else "flex",
        "--sepal-drawer-width": f"{drawer_px}px",
        "--sepal-top-reserved": f"{top_px}px",
        "--sepal-bottom-reserved": bottom_reserved,
    }

    def push_insets():
        if map_widget is None or not hasattr(map_widget, "set_insets"):
            return
        if narrow:
            # the map already sits below the belt and above the bottom band
            map_widget.set_insets()
        else:
            # the drawer and the right panel overlap the map, which spans the window
            map_widget.set_insets(left=drawer_px, right=right_px)

    solara.use_effect(
        push_insets, [id(map_widget), drawer_px, right_px, narrow, has_panel, panel_open]
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
        f"--sepal-mapapp-top: {top_px}px; --sepal-mapapp-bottom: {bottom_reserved}"
    )

    step_slots = {k: s for k, s in by_key.items() if s.get("display") == "step" and _has_content(s)}
    dialog_slots = {k: s for k, s in by_key.items() if _is_dialog(s) and _has_content(s)}
    active_index = keys.index(active_key) if active_key in by_key else None

    # Keyed, so that a conditional child coming or going does not move the
    # children after it, which would rebuild them.
    with rv.Html(tag="div", class_=" ".join(classes), style_=local_vars) as main:
        solara.Style(CSS)
        with rv.DefaultsProvider(defaults=DEFAULTS):
            ViewportBridge(
                css_vars=css_vars,
                body_class="sepal-modal-open" if modal else "",
                event_window_size=set_window,
            ).key("viewport-bridge")

            if has_map:
                MapContainer(
                    map_widget,
                    collapsible=not pinned and not rail,
                    on_collapse=collapse_if_unpinned,
                    overlays=map_overlays,
                ).key("map")

            if step_slots:
                with rv.Sheet(
                    tile=True,
                    elevation=0,
                    class_="step-content-container sepal-mapapp__step",
                    style_="" if active_key in step_slots else "display: none",
                ).key("steps"):
                    for key, step in step_slots.items():
                        Slot(
                            step.get("content"),
                            style_="" if key == active_key else "display: none",
                        ).key(f"step:{key}")

            links = external_links(repo_url, docs_url)
            if narrow:
                Belt(
                    app_title=app_title,
                    app_icon=app_icon,
                    width=width,
                    has_map=has_map,
                    steps=steps,
                    active_index=active_index,
                    disabled=modal,
                    links=links,
                    theme_state=state,
                    locales=locales,
                    on_map=show_map,
                    on_step=activate,
                ).key("belt")
            else:
                Drawer(
                    app_title=app_title,
                    app_icon=app_icon,
                    has_map=has_map,
                    steps=steps,
                    active_index=active_index,
                    rail=rail,
                    pinned=pinned,
                    disabled=modal,
                    links=links,
                    theme_state=state,
                    locales=locales,
                    on_map=show_map,
                    on_step=activate,
                    on_pin=lambda: set_pinned(not pinned),
                ).key("drawer")
                DrawerToggle(rail=rail, on_click=lambda: set_rail(not rail)).key("drawer-toggle")

            if has_panel:
                RightPanel(
                    config=right_panel_config,
                    sections=right_panel_content,
                    footer=right_panel_footer,
                    open=panel_open,
                    on_open=set_panel_open,
                    narrow=narrow,
                ).key("right-panel")

            if dialog_slots:
                size = dialog_step or {}
                StepDialog(
                    open=modal,
                    active_key=active_key,
                    dialog_steps=dialog_slots,
                    width=clamp(
                        (size.get("width"), dialog_width, 800), width, width - drawer_px - 40
                    ),
                    height=clamp((size.get("height"),), height, height - 80),
                    fullscreen=dialog_fullscreen,
                    on_close=close_dialog,
                    on_action=on_action,
                ).key("dialog")

    return main
