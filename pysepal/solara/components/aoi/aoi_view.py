"""Solara-native AOI (Area of Interest) selection component.

Usage:
    from pysepal.solara.components.aoi import AoiView, AoiResult

    @solara.component
    def MyApp():
        aoi = solara.use_reactive(None)

        AoiView(
            value=aoi,
            methods="ALL",
            gee=True
        )

        # Access AOI data when available
        if aoi.value:
            print(f"Selected: {aoi.value.name}")
"""

from typing import Any, Callable, Dict, List, Optional, Union

import reacton.ipyvuetify as rv
import solara
from deprecated.sphinx import versionadded

from pysepal import mapping as sm
from pysepal.mapping import get_ipygeojson
from pysepal.message import ms
from pysepal.scripts import utils as su
from pysepal.solara.components.aoi.admin import (
    fetch_admin_bounds_async,
    process_admin,
)
from pysepal.solara.components.aoi.aoi_result import AoiResult
from pysepal.solara.components.aoi.asset import process_asset
from pysepal.solara.components.aoi.draw import process_draw
from pysepal.solara.components.aoi.points import process_points
from pysepal.solara.components.aoi.shape import process_shape
from pysepal.solara.components.aoi.wms_utils import (
    WMS_PREVIEW_LAYER_NAME,
    create_wms_preview_layer,
)
from pysepal.solara.components.inputs.admin_selector import AdminLevelSelector
from pysepal.solara.components.inputs.asset_select import AssetSelectComponent
from pysepal.solara.components.inputs.point_selector import PointsSelectorComponent
from pysepal.solara.components.inputs.vector_selector import VectorSelectorComponent
from pysepal.solara.components.task_button import TaskButtonComponent, use_task_button
from pysepal.solara.notifications import use_notifications
from pysepal.solara.notifications.notifier import NoopNotifier
from pysepal.solara.utils import get_current_gee_interface

__all__ = ["AoiView", "MethodSelect", "AoiResult"]

# Method type constants
CUSTOM: str = ms.aoi_sel.custom
ADMIN: str = ms.aoi_sel.administrative

# Available selection methods
METHODS: Dict[str, Dict[str, str]] = {
    "ADMIN0": {"name": ms.aoi_sel.adm[0], "type": ADMIN},
    "ADMIN1": {"name": ms.aoi_sel.adm[1], "type": ADMIN},
    "ADMIN2": {"name": ms.aoi_sel.adm[2], "type": ADMIN},
    "SHAPE": {"name": ms.aoi_sel.vector, "type": CUSTOM},
    "DRAW": {"name": ms.aoi_sel.draw, "type": CUSTOM},
    "POINTS": {"name": ms.aoi_sel.points, "type": CUSTOM},
    "ASSET": {"name": ms.aoi_sel.asset, "type": CUSTOM},
}


@solara.component
def MethodSelect(
    methods: Union[str, List[str]] = "ALL",
    gee: bool = True,
    map_: Optional[sm.SepalMap] = None,
    value: Union[str, solara.Reactive[str]] = "",
    on_value: Optional[Callable[[str], None]] = None,
):
    """A method selector for AOI selection.

    Lists available methods for AOI selection. 'ALL' will select all available methods.
    'ADMIN' only the admin methods, 'CUSTOM' only the custom methods.
    Individual methods can be added (e.g., ['ADMIN0', 'SHAPE']) or removed (e.g., ['-DRAW', '-ASSET']).

    Args:
        methods: A list of methods from the available list
        gee: Whether to bind to Earth Engine or not
        map_: Link the aoi_view to a custom SepalMap to display the output
        value: Current selected method (can be reactive)
        on_value: Callback when method changes

    Returns:
        None
    """
    reactive_value = solara.use_reactive(value, on_value)
    del value, on_value

    # Create the method list based on input
    if methods == "ALL":
        method_dict = METHODS.copy()
    elif methods == "ADMIN":
        method_dict = {k: v for k, v in METHODS.items() if v["type"] == ADMIN}
    elif methods == "CUSTOM":
        method_dict = {k: v for k, v in METHODS.items() if v["type"] == CUSTOM}
    elif isinstance(methods, list):
        if any(m[0] == "-" for m in methods) and not all(m[0] == "-" for m in methods):
            raise ValueError("Cannot mix adding and removing methods")

        if methods[0][0] == "-":
            to_remove = [method[1:] for method in methods]
            method_dict = {k: v for k, v in METHODS.items() if k not in to_remove}
        else:
            method_dict = {k: METHODS[k] for k in methods if k in METHODS}
    else:
        raise ValueError("Invalid methods parameter")

    # Clean the list from things we can't use
    if not gee:
        method_dict.pop("ASSET", None)
    if map_ is None:
        method_dict.pop("DRAW", None)

    # Build the item list with headers
    prev_type = None
    items = []
    for k, m in method_dict.items():
        current_type = m["type"]

        if prev_type != current_type:
            items.append({"header": current_type})
        prev_type = current_type

        items.append({"text": m["name"], "value": k})

    with rv.Select(
        label=ms.aoi_sel.method,
        items=items,
        v_model=reactive_value.value,
        dense=True,
        on_v_model=reactive_value.set,
    ):
        pass


@solara.component
@versionadded(version="3.1", reason="Pure Solara AOI selection component")
def AoiView(
    value: Union[AoiResult, solara.Reactive[Optional[AoiResult]]] = None,
    on_value: Optional[Callable[[Optional[AoiResult]], None]] = None,
    loading: Union[bool, solara.Reactive[bool]] = False,
    on_loading: Optional[Callable[[bool], None]] = None,
    methods: Union[str, List[str]] = "ALL",
    map_: Optional[sm.SepalMap] = None,
    gee: bool = True,
    map_style: Optional[dict] = None,
    file_initial_folder: str = "",
    clear_ref: Optional[Any] = None,
):
    """Solara-native component for AOI (Area of Interest) selection.

    Provides multiple selection methods including administrative boundaries (GADM/GAUL),
    vector files, drawn shapes, points, and Earth Engine assets.

    Args:
        value: AoiResult containing AOI data. Can be reactive.
        on_value: Callback function called when AOI is selected/updated
        loading: Whether the component is in loading state
        on_loading: Callback when loading state changes
        methods: Methods to enable ('ALL', 'ADMIN', 'CUSTOM', or list of method names)
        map_: Link to a SepalMap instance for drawing and display
        gee: Whether to bind to Earth Engine
        map_style: Custom style for AOI display on map
        file_initial_folder: Initial folder for file-based method pickers (SHAPE, POINTS)
        clear_ref: Optional ref that receives a clear callback for external reset.
            The clear callback preserves the currently selected method so the
            user can retry without reselecting it.

    Example:
        ```python
        @solara.component
        def MyApp():
            aoi = solara.use_reactive(None)

            with solara.Column():
                AoiView(value=aoi, map_=my_map, gee=False)

                if aoi.value:
                    solara.Success(f"Selected: {aoi.value.name}")
        ```

    Returns:
        None. AOI data is passed through value/on_value as AoiResult.
    """
    # Normalize value/loading to reactive
    reactive_value = solara.use_reactive(value, on_value)
    reactive_loading = solara.use_reactive(loading, on_loading)
    del value, on_value, loading, on_loading

    # Validate GEE consistency between map and AoiView
    if map_ is not None and hasattr(map_, "gee"):
        if map_.gee != gee:
            raise ValueError(
                f"GEE setting mismatch: AoiView has gee={gee} but map has gee={map_.gee}. "
                f"Both must have the same GEE setting for proper functionality."
            )

    # Initialize Earth Engine once
    def _ensure_ee():
        if gee:
            su.init_ee()
        return None

    solara.use_effect(_ensure_ee, [gee])

    # Get DrawControl if map is provided
    aoi_dc = map_.dc if map_ else None

    selected_method = solara.use_reactive("")
    admin_code = solara.use_reactive(None)
    draw_name = solara.use_reactive("")
    shape_data = solara.use_reactive(None)
    points_data = solara.use_reactive(None)
    asset_data = solara.use_reactive(None)
    asset_loading = solara.use_reactive(False)

    # Notification system (replaces embedded alert). When no
    # NotificationProvider is mounted, `notifications` is a NoopNotifier
    # and user feedback is published inline instead.
    notifications = use_notifications()
    fallback_message = solara.use_reactive("")
    fallback_level = solara.use_reactive("info")

    def _clear_map_layers():
        if not map_:
            return

        for layer in list(map_.layers):
            if hasattr(layer, "name") and layer.name in ["aoi", WMS_PREVIEW_LAYER_NAME]:
                try:
                    map_.remove_layer(layer)
                except Exception:
                    # Layer may already be detached by another cleanup path.
                    pass

    def _sync_draw_control(active_method: str = ""):
        if not (map_ and aoi_dc):
            return

        try:
            aoi_dc.clear()
            if active_method == "DRAW":
                if aoi_dc not in map_.controls:
                    map_.add_control(aoi_dc)
            elif aoi_dc in map_.controls:
                map_.remove_control(aoi_dc)
        except Exception:
            # Control may already be detached by another cleanup path.
            pass

    def _clear_current_aoi(
        *,
        reset_method: bool = False,
        active_method: Optional[str] = None,
        reset_loading: bool = False,
        clear_value: bool = True,
    ):
        """Drop the current selection and everything it put on the map.

        Args:
            reset_method: Whether to also clear the selected method.
            active_method: The method to sync the draw control to, if not the
                currently selected one.
            reset_loading: Whether to lower the loading flag.
            clear_value: Whether to also reset ``value`` to None. ``value`` may be a
                reactive owned by the host app, which ``use_reactive`` passes straight
                through. Only user-driven clears may null it; teardown must not.
        """
        if reset_loading:
            reactive_loading.set(False)

        if clear_value:
            reactive_value.set(None)
        admin_code.set(None)
        draw_name.set("")
        shape_data.set(None)
        points_data.set(None)
        asset_data.set(None)
        fallback_message.set("")
        fallback_level.set("info")

        _clear_map_layers()
        _sync_draw_control(
            active_method
            if active_method is not None
            else ("" if reset_method else selected_method.value)
        )

        if reset_method:
            selected_method.set("")

    # Register clear callback for external use
    def _register_clear():
        if clear_ref is not None:

            def clear():
                # Preserve the currently selected method so the user can retry
                # immediately after clearing the previous AOI.
                _clear_current_aoi()

            clear_ref.current = clear

    solara.use_effect(_register_clear, [])

    # Track the current task in the notification system
    task_tracker_ref = solara.use_ref(None)

    async def process_aoi() -> str:
        """Process the selected AOI."""
        method = selected_method.value
        tracker = notifications.track(f"Processing AOI ({method})")
        task_tracker_ref.current = tracker
        tracker.__enter__()

        # Get session-backed GEE interface (uses EESession async methods)
        gee_interface = get_current_gee_interface() if gee else None

        try:
            tracker.step("Validating input...")

            if method in ["ADMIN0", "ADMIN1", "ADMIN2"]:
                if not admin_code.value:
                    raise ValueError(f"Please select a {method} region")

                tracker.step(f"Fetching {method} boundaries...")
                result = await process_admin(
                    method=method,
                    admin_code=admin_code.value,
                    gee=gee,
                    gee_interface=gee_interface,
                )

            elif method == "DRAW":
                if aoi_dc is None:
                    raise ValueError("No DrawControl available")

                features = aoi_dc.to_json()
                if not features.get("features"):
                    raise ValueError("No drawn features found. Please draw an area on the map.")

                tracker.step("Processing drawn features...")
                result = process_draw(
                    geo_json=features,
                    name=draw_name.value,
                    gee=gee,
                )

            elif method == "SHAPE":
                if not shape_data.value or not shape_data.value.get("pathname"):
                    raise ValueError("Please select a vector file")

                tracker.step("Processing vector file...")
                result = await process_shape(**shape_data.value, gee=gee)

            elif method == "POINTS":
                if not points_data.value or not points_data.value.get("pathname"):
                    raise ValueError("Please select a points file and id/lat/lng columns")

                tracker.step("Processing points file...")
                result = await process_points(**points_data.value, gee=gee)

            elif method == "ASSET":
                if not asset_data.value or not asset_data.value.get("asset_id"):
                    raise ValueError("Please select a GEE asset")

                tracker.step("Processing GEE asset...")
                result = await process_asset(
                    asset_id=asset_data.value["asset_id"],
                    asset_type=asset_data.value["type"],
                    column=asset_data.value.get("column", "ALL"),
                    value=asset_data.value.get("value"),
                )

            else:
                raise ValueError("Please select a method")

            # Update the map if available
            if map_ and result:
                tracker.step("Updating map...")

                _clear_map_layers()

                # Add new AOI layer
                if gee and result.feature_collection:
                    await map_.add_ee_layer_async(
                        result.feature_collection,
                        map_style or {},
                        "aoi",
                        autocenter=True,
                    )
                elif result.admin is not None:
                    level = int(method[-1])
                    wms_layer = create_wms_preview_layer(
                        level=level,
                        admin_code=result.admin,
                        name="aoi",
                    )
                    map_.add_layer(wms_layer)

                    bounds = await fetch_admin_bounds_async(level=level, admin_code=result.admin)
                    map_.zoom_bounds(bounds)
                elif result.gdf is not None:
                    geojson_layer = get_ipygeojson(result.gdf, result.name, map_style)
                    map_.add_layer(geojson_layer, key="aoi")
                    map_.zoom_bounds(result.gdf.total_bounds)

            # Update reactive value
            reactive_value.set(result)

            tracker.complete()
            return ms.aoi_sel.complete

        except BaseException:
            tracker.__exit__(*__import__("sys").exc_info())
            raise

    # Run AOI processing as async task
    # prefer_threaded=False: run on the stable kernel event loop instead of
    # spawning a new loop per invocation, which causes "bound to a different
    # event loop" errors on start/cancel/start cycles (eeclient's asyncio
    # primitives bind to the first loop they see).
    task = solara.lab.use_task(
        process_aoi,
        dependencies=None,
        raise_error=False,
        prefer_threaded=False,
    )

    has_notifications = not isinstance(notifications, NoopNotifier)

    # Handle task state changes (loading + toast for success)
    def handle_task_state():
        if task.pending:
            reactive_loading.set(True)
            fallback_message.set("")
            fallback_level.set("info")
        elif task.finished:
            reactive_loading.set(False)
            if task.value:
                if has_notifications:
                    notifications.success(task.value)
                else:
                    fallback_message.set(task.value)
                    fallback_level.set("success")
        elif task.error:
            reactive_loading.set(False)
            # The TaskTracker already published an error toast if a
            # NotificationProvider is mounted. If it is not, surface the
            # error inline so consumers without a provider still see it.
            if not has_notifications:
                fallback_message.set(str(task.exception))
                fallback_level.set("error")
        elif task.cancelled:
            reactive_loading.set(False)
            if has_notifications:
                notifications.cancel("Process cancelled")
            else:
                fallback_message.set("Process cancelled")
                fallback_level.set("info")

    solara.use_effect(handle_task_state, [task.pending, task.finished, task.error, task.cancelled])

    def start_process():
        """Trigger the background process."""
        reactive_loading.set(True)
        fallback_message.set("")
        fallback_level.set("info")
        task()

    # Handle method changes
    def on_method_change():
        if selected_method.value:
            _clear_current_aoi(active_method=selected_method.value)

    solara.use_effect(on_method_change, [selected_method.value])

    # Cleanup on unmount
    def _cleanup():
        def cleanup():
            # Note: We don't cancel the task here because task.cancel() raises
            # _CancelledErrorInOurTask which propagates up. The task will be
            # garbage collected when the component unmounts.

            # Release only what this picker owns. `value` belongs to the caller —
            # use_reactive passes a host-owned reactive straight through — and
            # unmounting the widget is not the user dropping their AOI.
            _clear_current_aoi(active_method="", reset_loading=True, clear_value=False)

            # Note: We intentionally do NOT reset map center/zoom on unmount
            # to avoid surprising side effects for host apps that own the map state

        return cleanup

    solara.use_effect(_cleanup, [id(map_) if map_ else None])

    # Prepare task button props (called unconditionally to satisfy hooks validator)
    btn_props = use_task_button(task, on_start=start_process)

    # Render
    with solara.Column(classes="mx-0 px-0"):
        # Method selector
        MethodSelect(
            methods=methods,
            gee=gee,
            map_=map_,
            value=selected_method,
        )

        # Method-specific inputs
        if selected_method.value in ["ADMIN0", "ADMIN1", "ADMIN2"]:
            AdminLevelSelector(
                method=selected_method.value,
                gee=gee,
                value=admin_code,
            )

        elif selected_method.value == "SHAPE":
            VectorSelectorComponent(
                gee=gee,
                initial_folder=file_initial_folder,
                value=shape_data,
            )

        elif selected_method.value == "POINTS":
            PointsSelectorComponent(
                initial_folder=file_initial_folder,
                value=points_data,
            )

        elif selected_method.value == "DRAW":
            if aoi_dc:
                with rv.TextField(
                    label="AOI Name (optional)",
                    v_model=draw_name.value,
                    on_v_model=draw_name.set,
                    outlined=True,
                    dense=True,
                ):
                    pass
            else:
                solara.Error("DrawControl not available. Please provide a map with DrawControl.")

        elif selected_method.value == "ASSET" and gee:
            session_gee_interface = get_current_gee_interface()
            AssetSelectComponent(
                gee_interface=session_gee_interface,
                value=asset_data,
                loading=asset_loading,
            )

        # Action buttons
        if selected_method.value:
            TaskButtonComponent(
                label="Select AOI",
                **btn_props,
                external_busy=asset_loading.value,
                small=True,
                block=True,
            )

        # Fallback inline feedback (only when no NotificationProvider is mounted)
        if fallback_message.value:
            if fallback_level.value == "success":
                solara.Success(fallback_message.value)
            elif fallback_level.value == "warning":
                solara.Warning(fallback_message.value)
            elif fallback_level.value == "error":
                solara.Error(fallback_message.value)
            else:
                solara.Info(fallback_message.value)
