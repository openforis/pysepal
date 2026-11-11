"""Test MapBtn widget."""

import ipyvuetify as v

from pysepal import mapping as sm
from pysepal._vuetify import IPYVUETIFY_V3


def test_init() -> None:
    """Init map btn in several ways."""
    # fa-solid icon
    map_btn = sm.MapBtn("fa-solid fa-folder")
    assert isinstance(map_btn, sm.MapBtn)
    assert isinstance(map_btn.children[0], v.Icon)
    # Vuetify 3 renders a Font Awesome name as is only behind the class: prefix
    prefix = "class:" if IPYVUETIFY_V3 else ""
    assert map_btn.children[0].children[0] == f"{prefix}fa-solid fa-folder"

    # mdi icon
    map_btn = sm.MapBtn("mdi-folder")
    assert isinstance(map_btn.children[0], v.Icon)
    assert map_btn.children[0].children[0] == "mdi-folder"

    # small text
    map_btn = sm.MapBtn("to")
    assert isinstance(map_btn.children[0], str)
    assert map_btn.children[0] == "TO"

    # long text
    map_btn = sm.MapBtn("toto")
    assert isinstance(map_btn.children[0], str)
    assert map_btn.children[0] == "TOT"

    return
