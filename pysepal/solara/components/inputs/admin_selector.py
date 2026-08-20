"""Cascading administrative level selector for AOI selection."""

from functools import partial
from typing import Callable, Optional, Tuple, Union

import reacton.ipyvuetify as rv
import solara
from deprecated.sphinx import versionadded, versionchanged

from pysepal.message import ms


@solara.component
@versionchanged(version="4.0", reason="The cascade is held as one tuple of codes")
@versionadded(version="3.1", reason="Self-contained admin level selector")
def AdminLevelSelector(
    method: str,
    gee: bool = True,
    value: Union[str, solara.Reactive[Optional[str]]] = None,
    on_value: Optional[Callable[[Optional[str]], None]] = None,
    codes: Union[Tuple[str, ...], solara.Reactive[Tuple[str, ...]]] = (),
    on_codes: Optional[Callable[[Tuple[str, ...]], None]] = None,
):
    """Administrative level selector with cascading dropdowns.

    The selection is held as one tuple of GAUL codes, level 0 first. Picking a code
    at one level truncates the tuple, so the child levels clear on their own.

    Args:
        method: The admin method ("ADMIN0", "ADMIN1", or "ADMIN2")
        gee: Whether to use Earth Engine (GAUL) or FAO WFS (local)
        codes: The full cascade, level 0 first. This is the two-way channel: set it
            to restore a previous selection.
        on_codes: Callback when the cascade changes.
        value: The final admin code. Derived from ``codes`` and output only —
            setting it does not move the dropdowns, because a single code cannot
            name its parents.
        on_value: Callback when the final admin code changes.

    Returns:
        None. The cascade is passed through codes/on_codes and the final code
        through value/on_value.

    Example:
        ```python
        @solara.component
        def MyApp():
            cascade = solara.use_reactive(("101", "1001"))

            AdminLevelSelector(method="ADMIN1", gee=False, codes=cascade)
        ```
    """
    # Hand a Reactive straight to use_reactive — it adopts it as-is. Only a plain
    # value is normalised, and `codes or ()` must never touch a Reactive: truthiness
    # on one raises TypeError("'len(...)' is not supported for a Reactive").
    reactive_codes = solara.use_reactive(
        codes if isinstance(codes, solara.Reactive) else tuple(codes or ()), on_codes
    )
    reactive_value = solara.use_reactive(value, on_value)
    del value, on_value, codes, on_codes

    items_0 = solara.use_reactive([])
    items_1 = solara.use_reactive([])
    items_2 = solara.use_reactive([])

    loading_0 = solara.use_reactive(False)
    loading_1 = solara.use_reactive(False)
    loading_2 = solara.use_reactive(False)

    target_level = {"ADMIN0": 0, "ADMIN1": 1, "ADMIN2": 2}.get(method, 0)

    picked = reactive_codes.value

    def _code_at(level: int) -> Optional[str]:
        return picked[level] if len(picked) > level else None

    def _select(level: int, code: Optional[str]) -> None:
        kept = reactive_codes.value[:level]
        reactive_codes.set(kept + (str(code),) if code else kept)

    async def _load_items(level: int, parent: Optional[str], into, loading) -> None:
        # Local import breaks the cycle: aoi/__init__ -> aoi_view -> this module.
        from pysepal.solara.components.aoi.admin import fetch_admin_items

        if level > target_level or (level > 0 and not parent):
            into.set([])
            return
        loading.set(True)
        try:
            into.set(fetch_admin_items(level=level, parent_code=parent or ""))
        finally:
            loading.set(False)

    async def _load_level_0():
        await _load_items(0, "", items_0, loading_0)

    async def _load_level_1():
        await _load_items(1, _code_at(0), items_1, loading_1)

    async def _load_level_2():
        await _load_items(2, _code_at(1), items_2, loading_2)

    solara.lab.use_task(_load_level_0, dependencies=[], raise_error=False)
    solara.lab.use_task(_load_level_1, dependencies=[_code_at(0), target_level], raise_error=False)
    solara.lab.use_task(_load_level_2, dependencies=[_code_at(1), target_level], raise_error=False)

    def _publish_final_code():
        reactive_value.set(_code_at(target_level))

    solara.use_effect(_publish_final_code, [picked, target_level])

    levels = (
        (0, items_0, loading_0, True),
        (1, items_1, loading_1, bool(_code_at(0))),
        (2, items_2, loading_2, bool(_code_at(1))),
    )

    with solara.Column(classes="pa-0 ma-0", style="gap: 8px;"):
        for level, items, loading, enabled in levels:
            if level > target_level:
                continue
            with rv.Select(
                label=ms.aoi_sel.adm[level],
                items=items.value,
                v_model=_code_at(level),
                clearable=True,
                dense=True,
                loading=loading.value,
                disabled=not enabled,
                on_v_model=partial(_select, level),
            ):
                pass
