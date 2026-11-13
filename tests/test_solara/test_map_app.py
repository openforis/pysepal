"""Tests for the native Solara MapApp shell, on the installed ipyvuetify major."""

from typing import Any, List

import ipyvuetify as v
import ipywidgets
import pytest
import solara
import traitlets

from pysepal.solara.components.map_app import MapApp, ThemeToggle
from pysepal.solara.components.map_app.shell import initial_step_id
from pysepal.solara.components.map_app.step_dialog import clamp
from pysepal.solara.theme import ThemeState


def walk(widget):
    """Walk the tree through children and slots."""
    yield widget
    children = list(getattr(widget, "children", ()) or ())
    for slot in getattr(widget, "v_slots", None) or []:
        slot_children = slot.get("children")
        children += slot_children if isinstance(slot_children, list) else [slot_children]
    for child in children:
        if child is not None and not isinstance(child, str):
            yield from walk(child)


class FakeMap(ipywidgets.DOMWidget):
    """The traits the shell pushes onto a SepalMap."""

    viewport_inset_left = traitlets.Int(0)
    viewport_inset_right = traitlets.Int(0)
    viewport_inset_bottom = traitlets.Int(0)
    canvas_width_px = traitlets.Int(0)
    canvas_height_px = traitlets.Int(0)

    def bind_theme_state(self, theme_state):
        self.bound = theme_state


def _classes(widget) -> str:
    return getattr(widget, "class_", None) or ""


def _with_class(root, name: str) -> List[Any]:
    return [w for w in walk(root) if name in _classes(w).split()]


def _nav_items(root) -> List[Any]:
    """Return the drawer entries, the widgets of ``NavItem.vue``."""
    return [w for w in walk(root) if hasattr(w, "vue_click")]


def _item(root, step_id) -> Any:
    items = [
        w
        for w in _nav_items(root)
        if (w.item_attributes or {}).get("data-step-id") == str(step_id)
    ]
    assert len(items) == 1, f"no drawer item for step {step_id}"
    return items[0]


def _map_item(root) -> Any:
    return next(
        w for w in _nav_items(root) if not w.href and "data-step-id" not in (w.item_attributes or {})
    )


def _bridge(root):
    return next(w for w in walk(root) if hasattr(w, "css_vars"))


def _dialog(root):
    return next(w for w in walk(root) if type(w).__name__ == "Dialog")


def _step_container(root):
    return _with_class(root, "sepal-mapapp__step")[0]


def _visible(widget) -> bool:
    return "display: none" not in (getattr(widget, "style_", None) or "")


def _text(widget) -> str:
    """Return the visible text under ``widget``: string children, icon names excluded."""
    return " ".join(
        c
        for w in walk(widget)
        if type(w).__name__ != "Icon"
        for c in (getattr(w, "children", ()) or ())
        if isinstance(c, str)
    ).strip()


def _steps():
    return [
        {"id": 1, "name": "Step", "display": "step", "content": [solara.Text("step one")]},
        {
            "id": 2,
            "name": "Dialog",
            "display": "dialog",
            "content": solara.Text("dialog two"),
            "actions": [{"label": "Next", "next": 1}, {"label": "Close", "close": True}],
        },
        {"id": 3, "name": "Action", "display": "action", "content": [solara.Text("hidden")]},
        {
            "id": 4,
            "name": "Toggle",
            "display": "step",
            "content": [],
            "right_panel_action": "toggle",
        },
    ]


SECTIONS = [{"title": "Tools", "content": [solara.Text("tools")]}]


def _render(**props):
    calls = {"current": [], "open": []}
    props.setdefault("on_current_step", calls["current"].append)
    props.setdefault("on_step_open", calls["open"].append)
    box, rc = solara.render(MapApp(**props), handle_error=False)
    return box, rc, calls


def test_initial_step_id_rules():
    steps = _steps()
    assert initial_step_id(steps, None, None, has_map=True) is None
    assert initial_step_id(steps, 2, None, has_map=True) == 2
    assert initial_step_id(steps, 3, None, has_map=True) is None  # not a step or dialog
    assert initial_step_id(steps, None, None, has_map=False) == 1
    assert initial_step_id(steps, 2, 1, has_map=True) == 1  # a named current_step wins


@pytest.mark.parametrize(
    "target,viewport,cap,default,expected",
    [
        (None, 0, 0, 800, 800),
        (900, 1200, 840, 800, 840),
        ("50%", 1000, 2000, 800, 500),
        ("50%", 0, 0, 800, 800),
        (None, 900, 820, None, None),
    ],
)
def test_clamp(target, viewport, cap, default, expected):
    assert clamp(target, viewport, cap, default) == expected


def test_step_display_step_replaces_map():
    box, _, calls = _render(main_map=FakeMap(), steps_data=_steps())
    assert not _visible(_step_container(box))

    _item(box, 1).vue_click(None)

    assert _visible(_step_container(box))
    assert "step one" in _text(_step_container(box))
    assert calls["current"] == [1]
    assert calls["open"] == [True]


def test_dialog_step_opens_and_closes():
    box, _, calls = _render(main_map=FakeMap(), steps_data=_steps())
    assert _dialog(box).v_model is False

    _item(box, 2).vue_click(None)
    assert _dialog(box).v_model is True
    assert "dialog two" in _text(_dialog(box))

    _dialog(box).v_model = False  # the user clicks outside or presses Esc
    assert _dialog(box).v_model is False
    assert calls["current"] == [2, None]


def test_dialog_next_action_moves_to_another_step():
    box, _, calls = _render(main_map=FakeMap(), steps_data=_steps())
    _item(box, 2).vue_click(None)

    next_btn = next(w for w in walk(_dialog(box)) if "Next" in (getattr(w, "children", None) or []))
    next_btn.fire_event("click", None)

    assert _dialog(box).v_model is False
    assert _visible(_step_container(box))
    assert calls["current"][-1] == 1


def test_action_step_reports_current_step_only():
    box, _, calls = _render(main_map=FakeMap(), steps_data=_steps())

    _item(box, 3).vue_click(None)

    assert calls["current"] == [3]
    assert not _visible(_step_container(box))
    assert _dialog(box).v_model is False
    assert "hidden" not in _text(box)


def test_step_without_content_runs_the_panel_action_only():
    box, _, calls = _render(
        main_map=FakeMap(), steps_data=_steps(), right_panel_content=SECTIONS, right_panel_open=True
    )
    panel = _with_class(box, "sepal-right-panel")[0]
    assert "sepal-right-panel--open" in _classes(panel)

    _item(box, 4).vue_click(None)

    panel = _with_class(box, "sepal-right-panel")[0]
    assert "sepal-right-panel--closed" in _classes(panel)
    assert calls["current"] == []


def test_map_entry_shows_the_map_again():
    box, _, calls = _render(main_map=FakeMap(), steps_data=_steps())
    _item(box, 1).vue_click(None)

    _map_item(box).vue_click(None)

    assert not _visible(_step_container(box))
    assert calls["current"] == [1, None]


def test_initial_step_opens_once_and_a_rerender_keeps_it_closed():
    title = solara.reactive("Title")

    @solara.component
    def Page():
        MapApp(app_title=title.value, main_map=FakeMap(), steps_data=_steps(), initial_step=2)

    box, _ = solara.render(Page(), handle_error=False)
    assert _dialog(box).v_model is True

    _dialog(box).v_model = False
    title.value = "Titre"  # a language switch re-renders the app with new names

    assert _dialog(box).v_model is False


def test_panel_content_survives_rerender():
    title = solara.reactive("Tools")

    @solara.component
    def Counter():
        count, set_count = solara.use_state(0)
        solara.Button(f"count {count}", on_click=lambda: set_count(count + 1))

    @solara.component
    def Page():
        MapApp(
            main_map=FakeMap(), right_panel_content=[{"title": title.value, "content": Counter()}]
        )

    _, rc = solara.render(Page(), handle_error=False)
    rc.find(v.Btn, children=["count 0"]).widget.click()
    rc.find(v.Btn, children=["count 1"]).assert_single()

    title.value = "Outils"

    rc.find(v.Btn, children=["count 1"]).assert_single()


def test_controlled_current_step():
    step = solara.reactive(None)

    @solara.component
    def Page():
        MapApp(
            main_map=FakeMap(),
            steps_data=_steps(),
            current_step=step.value,
            on_current_step=step.set,
        )

    box, _ = solara.render(Page(), handle_error=False)
    step.value = 1
    assert _visible(_step_container(box))

    step.value = None
    assert not _visible(_step_container(box))


def test_wide_window_publishes_layout_vars_and_insets():
    fake = FakeMap()
    box, _, _ = _render(
        main_map=[fake],
        right_panel_content=SECTIONS,
        right_panel_config={"width": 380},
        right_panel_open=True,
    )
    _bridge(box).vue_window_size({"w": 1400, "h": 900})

    css_vars = _bridge(box).css_vars
    assert css_vars["--sepal-drawer-width"] == "320px"
    assert css_vars["--sepal-right-panel-width"] == "380px"
    assert css_vars["--sepal-right-panel-open"] == "1"
    assert css_vars["--sepal-bottom-reserved"] == "0px"
    assert (fake.viewport_inset_left, fake.viewport_inset_right) == (320, 380)
    assert (fake.canvas_width_px, fake.canvas_height_px) == (1400, 900)
    assert isinstance(fake.bound, ThemeState)


def test_narrow_window_docks_panel_at_bottom():
    fake = FakeMap()
    box, _, _ = _render(main_map=fake, right_panel_content=SECTIONS, right_panel_open=True)

    _bridge(box).vue_window_size({"w": 800, "h": 600})

    root = _with_class(box, "sepal-mapapp")[0]
    assert "sepal-mapapp--narrow-bottom" in _classes(root)
    assert "sepal-right-panel--narrow" in _classes(_with_class(box, "sepal-right-panel")[0])
    assert "sepal-mapapp__drawer--rail" in _classes(_with_class(box, "sepal-mapapp__drawer")[0])
    assert _bridge(box).css_vars["--sepal-bottom-reserved"] == "45vh"
    assert _bridge(box).css_vars["--sepal-right-panel-width"] == "0px"
    assert (fake.viewport_inset_left, fake.viewport_inset_right) == (60, 0)
    assert fake.viewport_inset_bottom == 270


def test_open_dialog_marks_the_body():
    box, _, _ = _render(main_map=FakeMap(), steps_data=_steps())
    assert _bridge(box).body_class == ""

    _item(box, 2).vue_click(None)

    assert _bridge(box).body_class == "sepal-modal-open"


@pytest.mark.parametrize(
    "repo,docs,expected",
    [
        ("", "", []),
        ("https://github.com/x/y", "", ["Source Code", "Report Bug"]),
        ("", "https://docs", ["Documentation"]),
    ],
)
def test_links_follow_the_urls(repo, docs, expected):
    box, _, _ = _render(main_map=FakeMap(), repo_url=repo, docs_url=docs)
    links = [w for w in _nav_items(box) if w.href]
    assert [link.title for link in links] == expected


def _theme_button(root):
    return next(w for w in walk(root) if hasattr(w, "vue_set_dark"))


def test_toggle_writes_what_the_browser_resolves():
    state = ThemeState(mode="dark")
    box, _ = solara.render(ThemeToggle(theme_state=state), handle_error=False)
    button = _theme_button(box)

    button.vue_set_mode("auto")  # a click
    assert (state.mode, button.mode) == ("auto", "auto")

    button.vue_set_dark(True)  # auto, resolved against the browser's preference
    assert (state.dark, solara.lab.theme.dark) == (True, True)


def test_toggle_follows_the_state_and_skips_auto_when_disabled():
    state = ThemeState(mode="light")
    box, _ = solara.render(ThemeToggle(theme_state=state, enable_auto=False), handle_error=False)
    button = _theme_button(box)

    button.vue_set_mode("auto")
    assert state.mode == "light"

    state.set_mode("dark")
    assert button.mode == "dark"


def test_drawer_items_still_click_after_the_rail_toggles():
    """A narrow window turns the drawer into a rail and back; the items must still answer."""
    box, _, calls = _render(main_map=FakeMap(), steps_data=_steps())
    _bridge(box).vue_window_size({"w": 800, "h": 600})
    _bridge(box).vue_window_size({"w": 1400, "h": 900})

    _item(box, 1).vue_click(None)

    assert calls["current"] == [1]
    assert _visible(_step_container(box))
