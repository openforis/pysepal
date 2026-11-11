"""Test the SepalWidget mixin."""

import subprocess
import sys
from pathlib import Path

import ipyvuetify as v

from pysepal._sepal_widget import SepalWidget, Tooltip

# `python -c` imports pysepal from its cwd; a test elsewhere chdirs and never restores.
REPO_ROOT = Path(__file__).resolve().parents[2]


class _Btn(v.Btn, SepalWidget):
    pass


def test_mixin_imports_without_sepalwidgets() -> None:
    """Check that the mixin does not pull in ``pysepal.sepalwidgets``."""
    code = (
        "import sys; import pysepal._sepal_widget; "
        "assert 'pysepal.sepalwidgets' not in sys.modules, 'sepalwidgets imported'"
    )
    subprocess.run([sys.executable, "-c", code], check=True, cwd=REPO_ROOT)


def test_hide_and_show_return_self() -> None:
    """Check that ``hide``/``show`` chain and toggle the ``d-none`` class."""
    btn = _Btn(children=["x"])

    assert btn.hide() is btn
    assert btn.viz is False
    assert "d-none" in btn.class_

    assert btn.show() is btn
    assert btn.viz is True
    assert "d-none" not in btn.class_


def test_tooltip_binds_the_activator() -> None:
    """Check that the tooltip binds its activator slot's props to the widget."""
    btn = _Btn(children=["x"])
    tooltip = Tooltip(btn, "hello")

    assert tooltip.children == ["hello"]
    assert tooltip.v_slots[0]["children"] is btn
    assert btn.v_bind == "tooltip.props"
