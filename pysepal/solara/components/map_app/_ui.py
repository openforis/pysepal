"""Small helpers of the MapApp shell."""

import solara
from ipywidgets import Widget


def as_children(content) -> list:
    """Return a section's ``content`` as a list of widgets or elements."""
    if content is None:
        return []
    if isinstance(content, (Widget, solara.Element)):
        return [content]
    return list(content)


def step_keys(steps, prefix: str) -> list:
    """Return one reacton key per step, from its ``id``.

    A repeated or missing ``id`` gets a numbered key, since reacton raises on a
    duplicate key and the legacy shell accepted such steps.
    """
    seen: dict = {}
    keys = []
    for step in steps:
        step_id = step.get("id")
        count = seen.get(step_id, 0)
        seen[step_id] = count + 1
        keys.append(f"{prefix}-{step_id}" + (f"#{count}" if count else ""))
    return keys
