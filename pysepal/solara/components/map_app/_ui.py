"""Small helpers of the MapApp shell."""

import math
from typing import Mapping, Optional, Sequence, Union

import reacton.ipyvuetify as rv
import solara
from ipywidgets import Widget


def as_children(content) -> list:
    """Return a section's ``content`` as a list of widgets or elements."""
    if content is None:
        return []
    if isinstance(content, (Widget, solara.Element)):
        return [content]
    return list(content)


@solara.component
def Slot(content, item_class: Optional[str] = None, **kwargs):
    """Render an app's ``content`` in a div, each item in a div of ``item_class`` if given.

    Reacton keys are flat within a component, so the app's elements get a
    component of their own: their keys cannot clash with the shell's.
    """
    children = as_children(content)
    if item_class is not None:
        children = [rv.Html(tag="div", class_=item_class, children=[c]) for c in children]
    return rv.Html(tag="div", children=children, **kwargs)


def to_px(size: Union[int, float, str, None], viewport: int = 0) -> Optional[float]:
    """Return ``size`` in px, or None when it is empty or does not read as a size.

    Args:
        size: A number, ``"600"``, ``"600px"``, or ``"NN%"`` of ``viewport``.
        viewport: The window size along that axis; 0 until it is measured, in
            which case a percentage reads as None.
    """
    if isinstance(size, str):
        text = size.strip().lower()
        try:
            if text.endswith("%"):
                size = viewport * float(text[:-1]) / 100 if viewport > 0 else None
            else:
                size = float(text.removesuffix("px"))
        except ValueError:
            return None
    if not isinstance(size, (int, float)) or not math.isfinite(size) or size <= 0:
        return None
    return size


def step_keys(steps: Sequence[Mapping]) -> list:
    """Return a unique key per step: the shell's handle on it and its reacton key.

    The key comes from the ``id``, so a step keeps it when steps around it come
    and go. Steps that share an id, or have none, are numbered in list order:
    the shell accepts them as the legacy one did.
    """
    keys: list = []
    for step in steps:
        base = key = repr(step.get("id"))
        n = 0
        while key in keys:
            n += 1
            key = f"{base}#{n}"
        keys.append(key)
    return keys
