"""Tests for the native Solara MapApp shell, on the installed ipyvuetify major."""

from typing import Any, List

import ipyvuetify as v
import ipywidgets
import pytest
import solara
import traitlets

from pysepal.solara.components.map_app import MapApp, ThemeToggle
from pysepal.solara.components.map_app._ui import step_keys
from pysepal.solara.components.map_app.drawer import belt_slots, split_belt
from pysepal.solara.components.map_app.shell import initial_step_index
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


def _items(root, step_id) -> List[Any]:
    return [
        w for w in _nav_items(root) if (w.item_attributes or {}).get("data-step-id") == str(step_id)
    ]


def _item(root, step_id) -> Any:
    items = _items(root, step_id)
    assert len(items) == 1, f"no drawer item for step {step_id}"
    return items[0]


def _map_item(root) -> Any:
    return next(
        w
        for w in _nav_items(root)
        if not w.href and "data-step-id" not in (w.item_attributes or {})
    )


def _bridge(root):
    return next(w for w in walk(root) if hasattr(w, "css_vars"))


def _dialog(root):
    return next(w for w in walk(root) if type(w).__name__ == "Dialog")


def _step_container(root):
    return _with_class(root, "sepal-mapapp__step")[0]


def _visible(widget) -> bool:
    return "display: none" not in (getattr(widget, "style_", None) or "")


def _shown_text(widget) -> str:
    """Return the text under ``widget``, leaving out the subtrees hidden with display: none."""
    if not _visible(widget) or type(widget).__name__ == "Icon":
        return ""
    parts = [
        child if isinstance(child, str) else _shown_text(child)
        for child in getattr(widget, "children", ()) or ()
        if child is not None
    ]
    return " ".join(p for p in parts if p).strip()


def _button(root, label: str):
    return next(w for w in walk(root) if label in (getattr(w, "children", None) or []))


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


def test_initial_step_rules():
    steps = _steps()

    def initial(initial_step, current_step, has_map=True):
        index = initial_step_index(steps, initial_step, current_step, has_map)
        return None if index is None else steps[index]["id"]

    assert initial(None, None) is None
    assert initial(2, None) == 2
    assert initial(3, None) is None  # not a step or dialog
    assert initial(None, None, has_map=False) == 1
    assert initial(2, 1) == 1  # a named current_step wins
    assert initial(2, 4) == 2  # unless it has no content
    no_ids = [{"name": "A", "display": "step", "content": [solara.Text("a")]}]
    assert initial_step_index(no_ids, None, None, has_map=False) == 0


def test_step_keys_are_unique_and_follow_the_ids():
    keys = step_keys([{"id": i} for i in (1, "1", 1, True, "1#1", None, None)])
    assert len(set(keys)) == len(keys)
    # A unique id keeps its key wherever the step sits.
    assert step_keys([{"id": 2}, {"id": 1}])[1] == step_keys([{"id": 1}])[0]


@pytest.mark.parametrize(
    "target,viewport,cap,default,expected",
    [
        (None, 0, 0, 800, 800),
        (900, 1200, 840, 800, 840),
        ("50%", 1000, 2000, 800, 500),
        ("50%", 0, 0, 800, 800),
        (None, 900, 820, None, None),
        ("600", 1000, 2000, 800, 600),
        ("600px", 1000, 2000, 800, 600),
        ("600px", 0, 0, 800, 600),
        (" 600PX ", 1000, 2000, 800, 600),
        ("33.5%", 1000, 2000, 800, 335),
        ("auto", 1000, 2000, 800, 800),
        ("auto", 1000, 2000, 500, 500),
        ("inf", 0, 0, 800, 800),
        ("nan", 0, 0, 800, 800),
        (float("inf"), 0, 0, 800, 800),
        ("-100", 1000, 640, 800, 640),
        (0, 1000, 2000, 800, 800),
    ],
)
def test_clamp(target, viewport, cap, default, expected):
    assert clamp((target, default), viewport, cap) == expected


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


def _assert_unlocked(box):
    assert _dialog(box).v_model is False
    assert _with_class(box, "sepal-mapapp__drawer--disabled") == []
    assert _bridge(box).body_class == ""


def test_moving_off_an_open_dialog_unlocks_the_drawer():
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
    _item(box, 2).vue_click(None)
    assert _bridge(box).body_class == "sepal-modal-open"

    step.value = 1  # the app moves on once the dialog's form is submitted

    _assert_unlocked(box)
    assert _visible(_step_container(box))
    _map_item(box).vue_click(None)
    assert step.value is None


def test_next_to_a_step_without_content_closes_the_dialog():
    filled = solara.reactive(False)
    opened = []

    @solara.component
    def Page():
        steps = [
            {
                "id": 1,
                "name": "Form",
                "display": "dialog",
                "content": [solara.Text("form")],
                "actions": [{"label": "Next", "next": 2}],
            },
            {
                "id": 2,
                "name": "Results",
                "display": "dialog",
                "content": [solara.Text("results")] if filled.value else [],
            },
        ]
        MapApp(main_map=FakeMap(), steps_data=steps, on_step_open=opened.append)

    box, _ = solara.render(Page(), handle_error=False)
    _item(box, 1).vue_click(None)

    _button(_dialog(box), "Next").fire_event("click", None)

    _assert_unlocked(box)
    assert opened == [True, False]
    filled.set(True)  # the results arrive later
    _assert_unlocked(box)


@pytest.mark.parametrize("panel_open", [False, True])
def test_next_to_a_panel_step_shows_the_panel(panel_open):
    steps = [
        {
            "id": 1,
            "name": "Form",
            "display": "dialog",
            "content": [solara.Text("form")],
            "actions": [{"label": "Next", "next": 2}],
        },
        {"id": 2, "name": "Results", "content": [], "right_panel_action": "toggle"},
    ]
    box, _, _ = _render(
        main_map=FakeMap(),
        steps_data=steps,
        right_panel_content=SECTIONS,
        right_panel_open=panel_open,
    )
    _item(box, 1).vue_click(None)

    _button(_dialog(box), "Next").fire_event("click", None)

    _assert_unlocked(box)
    panel = _with_class(box, "sepal-right-panel")[0]
    assert "sepal-right-panel--open" in _classes(panel)


def test_current_step_does_not_open_a_step_without_content():
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

    step.value = 4

    assert not _visible(_step_container(box))
    assert _map_item(box).active


@solara.component
def Counter(tag: str):
    count, set_count = solara.use_state(0)
    solara.Button(f"{tag} {count}", on_click=lambda: set_count(count + 1))


def _assert_counter_survives(rc, flip):
    rc.find(v.Btn, children=["panel 0"]).widget.click()
    button = rc.find(v.Btn, children=["panel 1"]).widget
    flip()
    # Hook state survives a rebuilt subtree too; only the same widget shows the
    # browser side (typed text, a map, scroll) survived.
    assert rc.find(v.Btn, children=["panel 1"]).widget is button


def test_panel_content_survives_a_step_getting_content():
    ready = solara.reactive(False)

    @solara.component
    def Page():
        content = [solara.Text("results")] if ready.value else []
        MapApp(
            main_map=FakeMap(),
            steps_data=[{"id": 1, "name": "Results", "display": "step", "content": content}],
            right_panel_content=[{"title": "Tools", "content": Counter("panel")}],
            right_panel_open=True,
        )

    _, rc = solara.render(Page(), handle_error=False)
    _assert_counter_survives(rc, lambda: ready.set(True))


@pytest.mark.parametrize("start,end", [("", "A description"), ("A description", "")])
@pytest.mark.parametrize("in_footer", [False, True])
def test_panel_content_survives_the_panel_description_changing(in_footer, start, end):
    desc = solara.reactive(start)

    @solara.component
    def Page():
        counter = Counter("panel")
        MapApp(
            main_map=FakeMap(),
            right_panel_config={"description": desc.value},
            right_panel_content=[{"title": "Tools", "content": [] if in_footer else counter}],
            right_panel_footer=[counter] if in_footer else [],
        )

    _, rc = solara.render(Page(), handle_error=False)
    _assert_counter_survives(rc, lambda: desc.set(end))


@pytest.mark.parametrize("field", ["title", "icon", "description"])
def test_section_content_survives_its_header_appearing(field):
    value = solara.reactive("")

    @solara.component
    def Page():
        MapApp(
            main_map=FakeMap(),
            right_panel_content=[{field: value.value, "content": Counter("panel")}],
        )

    _, rc = solara.render(Page(), handle_error=False)
    _assert_counter_survives(rc, lambda: value.set("mdi-cog" if field == "icon" else "Text"))


def test_user_element_keys_do_not_clash_with_the_shell():
    steps = [
        {"id": 1, "name": "A", "display": "step", "content": [solara.Text("a").key("map")]},
        {"id": 2, "name": "B", "display": "step", "content": [solara.Text("b").key("map")]},
        {
            "id": 3,
            "name": "C",
            "display": "dialog",
            "content": [solara.Text("c").key("action-0")],
            "actions": [{"label": "Close", "close": True}],
        },
    ]
    box, _, _ = _render(
        main_map=FakeMap(),
        steps_data=steps,
        initial_step=1,
        right_panel_content=[
            {"title": "T", "content": [solara.Text("x"), solara.Text("y").key("content-0")]}
        ],
        right_panel_footer=[solara.Text("f").key("section-0")],
    )

    assert _shown_text(_step_container(box)) == "a"


@pytest.mark.parametrize("display", ["step", "dialog"])
def test_steps_sharing_an_id_open_one_at_a_time(display):
    steps = [
        {"id": 7, "name": name, "display": display, "content": [solara.Text(name * 3)]}
        for name in "CD"
    ]
    box, _, calls = _render(main_map=FakeMap(), steps_data=steps)

    _items(box, 7)[1].vue_click(None)

    shown = _shown_text(_step_container(box) if display == "step" else _dialog(box))
    assert "DDD" in shown and "CCC" not in shown
    assert [item.active for item in _items(box, 7)] == [False, True]
    assert calls["current"] == [7]


def test_a_shared_id_keeps_its_state_when_an_earlier_step_loses_content():
    first_has_content = solara.reactive(True)

    @solara.component
    def Page():
        MapApp(
            main_map=FakeMap(),
            steps_data=[
                {
                    "id": 5,
                    "name": "A",
                    "display": "step",
                    "content": [Counter("A")] if first_has_content.value else [],
                },
                {"id": 5, "name": "B", "display": "step", "content": [Counter("B")]},
            ],
        )

    _, rc = solara.render(Page(), handle_error=False)
    rc.find(v.Btn, children=["A 0"]).widget.click()

    first_has_content.set(False)

    rc.find(v.Btn, children=["B 0"]).assert_single()


def test_steps_without_an_id_open_and_are_not_the_map():
    steps = [{"name": n, "display": "step", "content": [solara.Text(n * 3)]} for n in "AB"]
    box, _, _ = _render(main_map=FakeMap(), steps_data=steps)
    assert _map_item(box).active
    assert [item.active for item in _items(box, None)] == [False, False]

    _items(box, None)[0].vue_click(None)

    assert _shown_text(_step_container(box)) == "AAA"
    assert not _map_item(box).active
    assert [item.active for item in _items(box, None)] == [True, False]


@pytest.mark.parametrize(
    "step_width,dialog_width,expected",
    [("auto", 500, 500), ("80vw", 500, 500), ("50%", 500, 500), (None, "inf", 800)],
)
def test_a_dialog_size_that_does_not_read_falls_back(step_width, dialog_width, expected):
    steps = [
        {"id": 1, "name": "D", "display": "dialog", "width": step_width, "content": ["text"]},
    ]
    box, _, _ = _render(
        main_map=FakeMap(), steps_data=steps, initial_step=1, dialog_width=dialog_width
    )

    assert _dialog(box).width == expected


def test_panel_width_reads_like_a_dialog_size():
    box, _, _ = _render(
        main_map=FakeMap(),
        right_panel_content=SECTIONS,
        right_panel_config={"width": "350px"},
        right_panel_open=True,
    )
    _bridge(box).vue_window_size({"w": 1400, "h": 900})

    assert _bridge(box).css_vars["--sepal-right-panel-width"] == "350px"
    assert "width: 350px" in _with_class(box, "sepal-right-panel")[0].style_


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
    assert _bridge(box).css_vars["--sepal-bottom-reserved"] == "45vh"
    assert _bridge(box).css_vars["--sepal-right-panel-width"] == "0px"
    assert (fake.viewport_inset_left, fake.viewport_inset_right) == (0, 0)
    assert fake.viewport_inset_bottom == 270


def _toggles(root) -> List[Any]:
    return [w for w in walk(root) if "control-btn" in _classes(w).split()]


def _icon(widget) -> str:
    return next(w for w in walk(widget) if type(w).__name__ == "Icon").children[0]


def test_the_drawer_toggle_keeps_its_colour_and_takes_the_panel_chevron():
    box, _, _ = _render(main_map=FakeMap(), right_panel_content=SECTIONS)
    _bridge(box).vue_window_size({"w": 1400, "h": 900})

    drawer, panel = _toggles(box)
    assert (drawer.color, panel.color) == ("primary", "secondary")
    assert (_icon(drawer), _icon(panel)) == ("mdi-chevron-left", "mdi-chevron-left")


def test_narrow_window_turns_the_drawer_into_a_top_belt():
    fake = FakeMap()
    box, _, calls = _render(
        app_title="Probe", main_map=fake, steps_data=_steps(), right_panel_content=SECTIONS
    )

    _bridge(box).vue_window_size({"w": 800, "h": 600})

    (belt,) = _with_class(box, "sepal-mapapp__belt")
    assert not _with_class(box, "sepal-mapapp__drawer")
    assert not _with_class(box, "sepal-mapapp__drawer-toggle")
    assert _with_class(box, "sepal-right-panel__tab")
    assert _text(_with_class(belt, "sepal-mapapp__belt-title")[0]) == "Probe"
    assert "sepal-mapapp__config" in _classes(belt.children[-1])
    css_vars = _bridge(box).css_vars
    assert css_vars["--sepal-top-reserved"] == "48px"
    assert css_vars["--sepal-drawer-width"] == "0px"
    assert css_vars["--sepal-bottom-reserved"] == "48px"
    assert css_vars["--sepal-notification-pill-display"] == "none"
    assert fake.canvas_height_px == 552

    _item(box, 1).vue_click(None)
    assert calls["current"] == [1]


@pytest.mark.parametrize(
    "width,title,slots",
    [(390, "Probe app", 2), (600, "Probe app", 7), (390, "x" * 40, 2), (300, "x" * 40, 1)],
)
def test_belt_slots_follow_the_window_and_the_title(width, title, slots):
    assert belt_slots(width, title) == slots


def test_split_belt_keeps_the_last_slot_for_the_menu():
    assert split_belt("abc", 3) == (["a", "b", "c"], [])
    assert split_belt("abcd", 3) == (["a", "b"], ["c", "d"])
    assert split_belt("abcd", 1) == ([], ["a", "b", "c", "d"])


def test_the_entries_that_do_not_fit_go_to_a_menu_that_still_clicks():
    steps = [
        {"id": i, "name": f"Step {i}", "display": "step", "content": [solara.Text(str(i))]}
        for i in range(1, 9)
    ]
    box, _, calls = _render(
        app_title="Probe app", main_map=FakeMap(), steps_data=steps, repo_url="https://x/y"
    )
    _bridge(box).vue_window_size({"w": 390, "h": 800})

    (belt,) = _with_class(box, "sepal-mapapp__belt")
    (menu,) = [w for w in walk(belt) if type(w).__name__ == "Menu"]
    in_menu = [w.title for w in _nav_items(menu)]
    assert in_menu == [f"Step {i}" for i in range(1, 9)] + ["Source Code", "Report Bug"]
    assert [w.title for w in _nav_items(belt) if w not in _nav_items(menu)] == ["Map"]

    _item(box, 8).vue_click(None)
    assert calls["current"] == [8]


def test_a_wide_window_shows_the_pill_and_reserves_no_top():
    box, _, _ = _render(main_map=FakeMap())
    _bridge(box).vue_window_size({"w": 1400, "h": 900})

    css_vars = _bridge(box).css_vars
    assert css_vars["--sepal-notification-pill-display"] == "flex"
    assert css_vars["--sepal-top-reserved"] == "0px"


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


def test_drawer_items_still_click_after_the_belt_comes_and_goes():
    """A narrow window turns the drawer into a belt and back; the items must still answer."""
    box, _, calls = _render(main_map=FakeMap(), steps_data=_steps())
    _bridge(box).vue_window_size({"w": 800, "h": 600})
    _bridge(box).vue_window_size({"w": 1400, "h": 900})

    _item(box, 1).vue_click(None)

    assert calls["current"] == [1]
    assert _visible(_step_container(box))
