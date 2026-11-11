"""Tests for the admin session panel."""

import inspect

import solara

from pysepal.solara.components import admin
from pysepal.solara.session_info import SessionInfo
from pysepal.solara.session_manager import SessionManager

from ._harness import of_type


def test_admin_uses_the_canonical_session_helpers():
    """The duplicates in admin.py drifted (no drive/theme flags); they are gone."""
    from pysepal.solara import utils

    assert admin.get_current_session_info is utils.get_current_session_info
    assert admin.get_sessions_overview is utils.get_sessions_overview


def test_admin_button_renders_without_a_session_manager():
    """Voila never runs on_kernel_start, so AdminButton renders manager-less."""
    assert SessionManager.is_initialized() is False

    box, _ = solara.render(admin.AdminButton(), handle_error=False)

    assert box.children[0].children == []


def test_rendering_admin_does_not_initialise_the_session_manager():
    """Building SessionManager() to read info flipped is_initialized() on."""
    solara.render(admin.AdminButton(), handle_error=False)

    assert SessionManager._instance is None
    assert SessionManager.is_initialized() is False


def test_admin_reads_session_info_by_attribute():
    """The payload is a frozen dataclass; .get() would raise."""
    source = inspect.getsource(admin._render_session_content)
    assert "session_info.get(" not in source
    assert "has_theme_state" not in source
    assert "session_info.scope_id" in source
    assert "session.has_drive_interface" in source


def test_admin_allowlist_is_configurable(monkeypatch):
    monkeypatch.setenv("PYSEPAL_ADMIN_USERS", "alice, bob")
    assert admin._admin_usernames() == {"alice", "bob"}


def test_admin_allowlist_defaults_to_admin(monkeypatch):
    monkeypatch.delenv("PYSEPAL_ADMIN_USERS", raising=False)
    assert admin._admin_usernames() == {"admin"}


def test_admin_gate_fails_closed_for_a_scope_less_caller(monkeypatch):
    """A caller with no resolvable scope must not see the admin panel.

    ``get_current_session_info()`` reports ``username=None`` for a scope that
    can't be resolved (it never falls back to the process/dev-auth identity's
    username). The gate must treat that ``None`` as "not admin", even under a
    permissive allowlist -- it must never render the panel for it.
    """
    monkeypatch.setenv("PYSEPAL_ADMIN_USERS", "admin")
    monkeypatch.setattr(
        admin,
        "get_current_session_info",
        lambda: SessionInfo(scope_id="process", username=None),
    )

    box, _ = solara.render(admin.AdminButton(), handle_error=False)

    assert box.children[0].children == []


class _Model:
    def export_data(self):
        return {"answer": 42}


def _render_admin_panel(monkeypatch):
    """Render the panel for an admin; the dialog content is built while it is closed."""
    monkeypatch.setenv("PYSEPAL_ADMIN_USERS", "admin")
    monkeypatch.setattr(
        admin,
        "get_current_session_info",
        lambda: SessionInfo(scope_id="probe", username="admin"),
    )
    box, rc = solara.render(admin.AdminButton(models=_Model()), handle_error=False)
    return box, rc


def test_admin_button_is_small(monkeypatch):
    box, rc = _render_admin_panel(monkeypatch)
    try:
        button = of_type(box, "Btn")[0]
        assert button.size == "small"
    finally:
        rc.close()


def test_admin_tabs_switch_their_content(monkeypatch):
    """The tab model must drive the window body."""
    box, rc = _render_admin_panel(monkeypatch)
    try:
        tabs = of_type(box, "Tabs")[0]
        window = of_type(box, "TabsWindow")[0]
        items = of_type(window, "TabsWindowItem")

        assert [tab.children[0] for tab in of_type(tabs, "Tab")] == ["Model Data", "Session Info"]
        assert len(items) == 2
        assert [tab.value for tab in of_type(tabs, "Tab")] == [0, 1]
        assert [item.value for item in items] == [0, 1]
        assert tabs.color == "primary"
        assert tabs.v_model == window.v_model == 0

        tabs.v_model = 1

        assert window.v_model == 1
    finally:
        rc.close()


def test_admin_model_card_is_outlined(monkeypatch):
    box, rc = _render_admin_panel(monkeypatch)
    try:
        dialog_card = of_type(box, "Card")[0]
        # The model data is read when the dialog opens.
        of_type(box, "Btn")[0].fire_event("click", {})
        cards = [card for card in of_type(box, "Card") if card is not dialog_card]
        assert [card.border for card in cards] == [""]
    finally:
        rc.close()
