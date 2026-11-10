"""Close the widgets a map component built."""

from typing import Iterable, List

from ipywidgets import Widget

# Only the traits that hold a widget's own parts. Others can point to shared
# widgets: every ipyvue widget references one module-level ForceLoad.
_PART_TRAITS = ("children", "v_slots", "widget", "layout", "style")


def _parts(widget: Widget) -> List:
    # _trait_values, not getattr: reading an unset trait would build its default,
    # and a control whose __init__ failed is still closed by Widget.__del__.
    values = widget._trait_values
    return [values.get(name) for name in _PART_TRAITS if name in widget.keys]


def close_tree(*roots, keep: Iterable[Widget] = ()) -> None:
    """Close each root and the widgets it is made of.

    A widget that is not closed stays in the kernel's widget registry and comms,
    and keeps whatever it references alive until the kernel ends. Only pass
    trees the caller built: nothing in them may belong to someone else.

    Args:
        roots: the widgets to close, in order
        keep: widgets to leave open, with everything below them
    """
    skip = {id(widget) for widget in keep}
    stack = list(reversed(roots))
    while stack:
        item = stack.pop()
        if isinstance(item, Widget):
            if id(item) in skip:
                continue
            skip.add(id(item))
            stack.extend(_parts(item))
            item.close()
        elif isinstance(item, (list, tuple)):
            stack.extend(item)
        elif isinstance(item, dict):
            stack.extend(item.values())


def close_parts(widget: Widget, keep: Iterable[Widget] = ()) -> None:
    """Close the widgets a widget is made of, but not the widget itself.

    Args:
        widget: the widget whose parts are closed
        keep: widgets to leave open, with everything below them
    """
    close_tree(*_parts(widget), keep=keep)
