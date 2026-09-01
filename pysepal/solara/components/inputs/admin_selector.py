"""Cascading administrative level selector for AOI selection."""

from typing import Callable, Optional, Union

import reacton.ipyvuetify as rv
import solara
from deprecated.sphinx import versionadded

from pysepal.message import msg


@solara.component
@versionadded(version="3.1", reason="Self-contained admin level selector")
def AdminLevelSelector(
    method: str,
    gee: bool = True,
    value: Union[str, solara.Reactive[Optional[str]]] = None,
    on_value: Optional[Callable[[Optional[str]], None]] = None,
):
    """Self-contained administrative level selector with cascading dropdowns.

    Manages internal state for cascading admin levels (0, 1, 2) and exposes
    only the final selected admin code. Provides a stable render tree regardless
    of the method (ADMIN0, ADMIN1, ADMIN2).

    Args:
        method: The admin method ("ADMIN0", "ADMIN1", or "ADMIN2")
        gee: Whether to use Earth Engine (GAUL) or FAO WFS (local)
        value: The final selected admin code (output only)
        on_value: Callback when the final admin code changes

    Returns:
        None. The final admin code is passed through value/on_value.

    Example:
        ```python
        @solara.component
        def MyApp():
            admin_code = solara.use_reactive(None)

            AdminLevelSelector(
                method="ADMIN1",
                gee=False,
                value=admin_code,
            )

            if admin_code.value:
                solara.Text(f"Selected: {admin_code.value}")
        ```
    """
    reactive_value = solara.use_reactive(value, on_value)
    del value, on_value

    # Internal state for each level - ALWAYS created (stable hooks)
    level_0 = solara.use_reactive(None)
    level_1 = solara.use_reactive(None)
    level_2 = solara.use_reactive(None)

    items_0 = solara.use_reactive([])
    items_1 = solara.use_reactive([])
    items_2 = solara.use_reactive([])

    loading_0 = solara.use_reactive(False)
    loading_1 = solara.use_reactive(False)
    loading_2 = solara.use_reactive(False)

    target_level = {"ADMIN0": 0, "ADMIN1": 1, "ADMIN2": 2}.get(method, 0)

    async def _load_level_0():
        # Local import breaks the cycle: aoi/__init__ -> aoi_view -> this module.
        from pysepal.solara.components.aoi.admin import fetch_admin_items

        loading_0.set(True)
        try:
            items = fetch_admin_items(level=0, parent_code="")
            items_0.set(items)
        finally:
            loading_0.set(False)

    solara.lab.use_task(_load_level_0, dependencies=[], raise_error=False)

    async def _load_level_1():
        from pysepal.solara.components.aoi.admin import fetch_admin_items

        if level_0.value and target_level >= 1:
            loading_1.set(True)
            try:
                items = fetch_admin_items(level=1, parent_code=level_0.value)
                items_1.set(items)
            finally:
                loading_1.set(False)
        else:
            items_1.set([])
        level_1.set(None)
        level_2.set(None)
        items_2.set([])

    solara.lab.use_task(
        _load_level_1,
        dependencies=[level_0.value, target_level],
        raise_error=False,
    )

    async def _load_level_2():
        from pysepal.solara.components.aoi.admin import fetch_admin_items

        if level_1.value and target_level >= 2:
            loading_2.set(True)
            try:
                items = fetch_admin_items(level=2, parent_code=level_1.value)
                items_2.set(items)
            finally:
                loading_2.set(False)
        else:
            items_2.set([])
        level_2.set(None)

    solara.lab.use_task(
        _load_level_2,
        dependencies=[level_1.value, target_level],
        raise_error=False,
    )

    def update_output():
        if target_level == 0:
            reactive_value.set(level_0.value)
        elif target_level == 1:
            reactive_value.set(level_1.value)
        elif target_level == 2:
            reactive_value.set(level_2.value)

    solara.use_effect(update_output, [level_0.value, level_1.value, level_2.value, target_level])

    with solara.Column(classes="pa-0 ma-0", style="gap: 8px;"):
        with rv.Select(
            label=msg("aoi_sel.adm.0"),
            items=items_0.value,
            v_model=level_0.value,
            clearable=True,
            dense=True,
            loading=loading_0.value,
            on_v_model=level_0.set,
        ):
            pass

        if target_level >= 1:
            with rv.Select(
                label=msg("aoi_sel.adm.1"),
                items=items_1.value,
                v_model=level_1.value,
                clearable=True,
                dense=True,
                loading=loading_1.value,
                disabled=not level_0.value,
                on_v_model=level_1.set,
            ):
                pass

        if target_level >= 2:
            with rv.Select(
                label=msg("aoi_sel.adm.2"),
                items=items_2.value,
                v_model=level_2.value,
                clearable=True,
                dense=True,
                loading=loading_2.value,
                disabled=not level_1.value,
                on_v_model=level_2.set,
            ):
                pass
