"""Tests for notification state model."""

from pysepal.solara.notifications.state import Toast, ToastType


def test_toast_effective_timeout_uses_default():
    assert Toast(message="ok", type=ToastType.SUCCESS).effective_timeout() == 3.0


def test_toast_effective_timeout_explicit_overrides():
    assert Toast(message="ok", type=ToastType.SUCCESS, timeout=20.0).effective_timeout() == 20.0


def test_error_toasts_stay_until_clicked():
    assert Toast(message="boom", type=ToastType.ERROR).effective_timeout() is None


def test_an_error_toast_can_still_time_out_when_asked():
    assert Toast(message="boom", type=ToastType.ERROR, timeout=5.0).effective_timeout() == 5.0
