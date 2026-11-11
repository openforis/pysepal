"""Tests for the task button and its use_task_button hook."""

from unittest.mock import MagicMock

import solara

from pysepal.solara.components.task_button import TaskButtonComponent, use_task_button

from ._harness import of_type


def test_use_task_button_returns_correct_keys():
    """use_task_button returns dict with running, on_start, on_cancel."""
    mock_task = MagicMock()
    mock_task.pending = False
    on_start = MagicMock()

    result = use_task_button(mock_task, on_start=on_start)

    assert "running" in result
    assert "on_start" in result
    assert "on_cancel" in result
    assert result["running"] is False
    assert result["on_start"] is on_start


def test_use_task_button_running_reflects_task_pending():
    """use_task_button running matches task.pending."""
    mock_task = MagicMock()
    mock_task.pending = True
    on_start = MagicMock()

    result = use_task_button(mock_task, on_start=on_start)

    assert result["running"] is True


def test_use_task_button_cancel_calls_task_cancel():
    """on_cancel from use_task_button calls task.cancel()."""
    mock_task = MagicMock()
    mock_task.pending = True
    on_start = MagicMock()

    result = use_task_button(mock_task, on_start=on_start)
    result["on_cancel"]()

    mock_task.cancel.assert_called_once()


def test_use_task_button_cancel_sets_reason_ref():
    """on_cancel sets cancel_reason_ref.current to 'user'."""
    mock_task = MagicMock()
    mock_task.pending = True
    on_start = MagicMock()
    reason_ref = MagicMock()
    reason_ref.current = None

    result = use_task_button(
        mock_task,
        on_start=on_start,
        cancel_reason_ref=reason_ref,
    )
    result["on_cancel"]()

    assert reason_ref.current == "user"


def test_use_task_button_cancel_handles_runtime_error():
    """on_cancel swallows RuntimeError from task.cancel()."""
    mock_task = MagicMock()
    mock_task.pending = True
    mock_task.cancel.side_effect = RuntimeError("already cancelled")
    on_start = MagicMock()

    result = use_task_button(mock_task, on_start=on_start)
    result["on_cancel"]()


def test_use_task_button_cancel_noop_when_not_pending():
    """on_cancel does nothing when task is not pending."""
    mock_task = MagicMock()
    mock_task.pending = False
    on_start = MagicMock()

    result = use_task_button(mock_task, on_start=on_start)
    result["on_cancel"]()

    mock_task.cancel.assert_not_called()


def _render_button(**kwargs):
    box, rc = solara.render(
        TaskButtonComponent(
            label="Run", icon="mdi-play", on_start=MagicMock(), on_cancel=MagicMock(), **kwargs
        ),
        handle_error=False,
    )
    rc.close()
    btn = of_type(box, "Btn")[0]
    return btn, of_type(btn, "Icon")[0]


def test_small_button_is_small():
    btn, icon = _render_button(small=True)

    assert btn.size == "small"
    assert icon.start is True
    # The button sizes its icon itself.
    assert icon.size is None


def test_default_button_has_no_size():
    btn, icon = _render_button()

    assert btn.size is None
    assert icon.start is True


def test_button_is_filled():
    """Card actions turn a button without a variant into a text button."""
    btn, _ = _render_button()

    assert btn.variant == "elevated"
