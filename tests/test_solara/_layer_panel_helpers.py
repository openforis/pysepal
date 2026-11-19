"""Helpers for asserting on a rendered LayerPanel, shared by the panel tests."""

from typing import Any, Iterator, List

from tests.test_solara._harness import walk


def _attr(widget: Any, name: str) -> Any:
    return (getattr(widget, "attributes", None) or {}).get(name)


def _tree(widget: Any) -> Iterator[Any]:
    """Walk children and the widgets held in ``v_slots`` (tooltip activators)."""
    yield widget
    for slot in getattr(widget, "v_slots", None) or []:
        child = slot.get("children")
        for item in child if isinstance(child, list) else [child]:
            if item is not None and not isinstance(item, str):
                yield from _tree(item)
    for child in getattr(widget, "children", ()) or ():
        if not isinstance(child, str):
            yield from _tree(child)


def row_ids(box: Any) -> List[str]:
    """Layer ids of the rendered rows, in display order."""
    sortable = next(w for w in walk(box) if hasattr(w, "vue_move"))
    return list(sortable.ids)


def role_widgets(box: Any, role: str) -> List[Any]:
    """Widgets tagged with ``data-role=role``, in document order."""
    return [w for w in _tree(box) if _attr(w, "data-role") == role]


def find_by_role(box: Any, role: str, layer_id: str) -> Any:
    """The widget with ``data-role=role`` for one layer."""
    return next(w for w in role_widgets(box, role) if _attr(w, "data-layer-id") == layer_id)


def click(widget: Any) -> None:
    """Fire a click on ``widget``."""
    widget.fire_event("click", {})


def find_visibility_toggle(box: Any, layer_id: str) -> Any:
    """The visibility button of a row."""
    return find_by_role(box, "visibility", layer_id)


def expand(box: Any, layer_id: str) -> None:
    """Expand a row."""
    click(find_by_role(box, "expand", layer_id))


def export_buttons(box: Any) -> List[str]:
    """Layer ids that show an Export button, after expanding every row."""
    for w in role_widgets(box, "expand"):
        click(w)
    return [_attr(w, "data-layer-id") for w in role_widgets(box, "export")]


def export_button(box: Any, layer_id: str) -> Any:
    """The Export button of a row."""
    return find_by_role(box, "export", layer_id)


def all_text(box: Any) -> str:
    """Every string in the tree: children, tooltip text and titles."""
    out: List[str] = []
    for w in _tree(box):
        out.extend(c for c in getattr(w, "children", ()) or () if isinstance(c, str))
        title = _attr(w, "title")
        if title:
            out.append(title)
    return " ".join(out)


def field_names(box: Any) -> List[str]:
    """Names of the restyle form fields, in order."""
    return [_attr(w, "data-field") for w in role_widgets(box, "field")]


def set_field(box: Any, name: str, value: Any) -> None:
    """Type ``value`` into a restyle form field."""
    next(w for w in role_widgets(box, "field") if _attr(w, "data-field") == name).v_model = value


def click_apply(box: Any) -> None:
    """Click the Apply button of the open restyle form."""
    click(role_widgets(box, "apply")[0])


def pick_basemap(box: Any, name: str) -> None:
    """Choose a basemap in the picker."""
    role_widgets(box, "basemap")[0].v_model = name


def spinner_count(box: Any) -> int:
    """Rows showing the pending spinner."""
    return sum(type(w).__name__ == "ProgressCircular" for w in _tree(box))


def button_icon(button: Any) -> str:
    """The icon name of an icon button."""
    return next(w.children[0] for w in _tree(button) if type(w).__name__ == "Icon")
