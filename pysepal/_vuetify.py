"""Write one widget call that renders on ipyvuetify 1 (Vuetify 2) and 3 (Vuetify 3).

``IPYVUETIFY_V3`` follows the rule ``solara.util.IPYVUETIFY_V3`` uses, so pysepal
and Solara always agree on the installed major. Each helper returns the props a
Vuetify 2 call wrote inline, spelled for the installed major; spread the result
into the widget call: ``rv.Select(items=..., **density())``.

The helpers read ``IPYVUETIFY_V3`` when they are called, not when they are
imported, so a test can monkeypatch it to cover both branches.
"""

import re
from pathlib import Path
from typing import Iterable, Optional, Union

import ipyvuetify

IPYVUETIFY_V3: bool = int(ipyvuetify.__version__.split(".")[0]) >= 3

_SIZES = ("x-small", "small", "large", "x-large")


def density(dense: bool = True) -> dict:
    """Return the props of a dense (compact) component."""
    if not dense:
        return {}
    return {"density": "compact"} if IPYVUETIFY_V3 else {"dense": True}


def size(name: Optional[str]) -> dict:
    """Return the props of a sized component (``"x-small"`` to ``"x-large"``)."""
    if name is None:
        return {}
    if name not in _SIZES:
        raise ValueError(f"size must be one of {_SIZES}, not {name!r}")
    return {"size": name} if IPYVUETIFY_V3 else {name.replace("-", "_"): True}


def btn_variant(*, text: bool = False, outlined: bool = False, depressed: bool = False) -> dict:
    """Return the style props of a button.

    Vuetify 3 has one ``variant`` where Vuetify 2 had a flag per style; when several
    flags are set, ``text`` wins over ``outlined``, which wins over ``depressed``.
    """
    if not IPYVUETIFY_V3:
        flags = {"text": text, "outlined": outlined, "depressed": depressed}
        return {key: True for key, value in flags.items() if value}
    for flag, variant in ((text, "text"), (outlined, "outlined"), (depressed, "flat")):
        if flag:
            return {"variant": variant}
    return {}


def icon_start() -> dict:
    """Return the props of an icon placed before a label."""
    return {"start": True} if IPYVUETIFY_V3 else {"left": True}


def field_variant(*, outlined: bool = False) -> dict:
    """Return the style props of a text field, select or combobox.

    Vuetify 3 fields default to ``filled``; ``underlined`` is the Vuetify 2 default look.
    """
    if IPYVUETIFY_V3:
        return {"variant": "outlined" if outlined else "underlined"}
    return {"outlined": True} if outlined else {}


def select_items(items: Iterable[Union[dict, str]]) -> list:
    """Return select/autocomplete items in the installed major's shape.

    pysepal writes items the Vuetify 2 way: ``{"text", "value", "disabled"}``,
    ``{"header": label}`` and ``{"divider": True}``. Vuetify 3 reads ``title``,
    takes item props from ``props`` and marks headers and dividers with ``type``.
    """
    items = list(items)
    if not IPYVUETIFY_V3:
        return items
    return [_v3_item(item) for item in items]


def _v3_item(item: Union[dict, str]) -> Union[dict, str]:
    if not isinstance(item, dict):
        return item
    if "header" in item:
        return {"type": "subheader", "title": item["header"]}
    if item.get("divider"):
        # without a title Vuetify 3 uses the whole item as one ("[object Object]")
        return {"type": "divider", "title": ""}
    converted = {("title" if key == "text" else key): value for key, value in item.items()}
    if converted.pop("disabled", False):
        converted["props"] = {**converted.get("props", {}), "disabled": True}
    return converted


def vuetify_markup(stem: Path) -> Path:
    """Return the markup file of a template for the installed major: ``<stem>.v2.vue`` or ``.v3.vue``."""
    return stem.with_suffix(".v3.vue" if IPYVUETIFY_V3 else ".v2.vue")


def compose_vue(markup: Path, script: Path) -> str:
    """Return a Vue template made of a per-major markup file and a shared script.

    The markup file holds ``<template>`` and ``<style>``; the script file holds the
    ``export default {...}`` both majors share, so the logic is written once.
    """
    text = markup.read_text()
    block = f"<script>\n{script.read_text().rstrip()}\n</script>\n"
    match = re.search(r"^<style", text, flags=re.MULTILINE)
    if match is None:
        return f"{text.rstrip()}\n\n{block}"
    return f"{text[: match.start()]}{block}\n{text[match.start():]}"
