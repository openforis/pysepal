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

import json
import logging
import weakref
from typing import Any, Callable, Collection, Dict, List, Optional, Union

import geopandas as gpd
import reacton.ipyvuetify as rv
import solara
from deprecated.sphinx import versionadded, versionchanged
from mapframe import Draw

from pysepal import mapping as sm
from pysepal.frontend import styles as ss
from pysepal.layers import LayerSpec, LayerStore, VectorStyle
from pysepal.message import msg
from pysepal.scripts import utils as su
from pysepal.solara.components.aoi.admin import (
    fetch_admin_bounds_async,
    process_admin,
)
from pysepal.solara.components.aoi.aoi_result import AoiResult
from pysepal.solara.components.aoi.aoi_spec import ADMIN_METHODS, AoiSpec
from pysepal.solara.components.aoi.asset import process_asset
from pysepal.solara.components.aoi.constants import (
    AOI_LAYER_ID,
    AOI_PREVIEW_LAYER_ID,
    admin_source_attribution,
)
from pysepal.solara.components.aoi.draw import process_draw
from pysepal.solara.components.aoi.points import process_points
from pysepal.solara.components.aoi.shape import process_shape
from pysepal.solara.components.aoi.wms_utils import create_wms_preview_layer
from pysepal.solara.components.inputs.admin_selector import AdminLevelSelector
from pysepal.solara.components.inputs.asset_select import AssetSelectComponent
from pysepal.solara.components.inputs.point_selector import PointsSelectorComponent
from pysepal.solara.components.inputs.vector_selector import VectorSelectorComponent
from pysepal.solara.components.task_button import TaskButtonComponent, use_task_button
from pysepal.solara.notifications import use_notifications
from pysepal.solara.notifications.notifier import NoopNotifier
from pysepal.solara.utils import get_current_gee_interface, user_files_available

__all__ = ["AoiResult", "AoiView", "MethodSelect"]

log = logging.getLogger(__name__)

# Who drew the AOI outline of a store: one token per AoiView, so a view another one took
# over from never removes what is now the newer owner's.
_OUTLINE_OWNERS: "weakref.WeakKeyDictionary[LayerStore, object]" = weakref.WeakKeyDictionary()
_DRAW_MODES = ("polygon", "rectangle", "circle")

# Method group identifiers. Codes, not words: they are compared in code below,
# so a translated value would break the comparison as soon as a user picks a
# language. Kept in step with AoiModel by tests/test_aoi/test_AoiModel.py.
CUSTOM: str = "custom"
ADMIN: str = "admin"

# Available selection methods. label_key is a catalogue key the caller renders
# with msg(), so the text follows the locale.
METHODS: Dict[str, Dict[str, str]] = {
    "ADMIN0": {"label_key": "aoi_sel.adm.0", "type": ADMIN},
    "ADMIN1": {"label_key": "aoi_sel.adm.1", "type": ADMIN},
    "ADMIN2": {"label_key": "aoi_sel.adm.2", "type": ADMIN},
    "SHAPE": {"label_key": "aoi_sel.vector", "type": CUSTOM},
    "DRAW": {"label_key": "aoi_sel.draw", "type": CUSTOM},
    "POINTS": {"label_key": "aoi_sel.points", "type": CUSTOM},
    "ASSET": {"label_key": "aoi_sel.asset", "type": CUSTOM},
}
TYPE_LABEL_KEYS: Dict[str, str] = {ADMIN: "aoi_sel.administrative", CUSTOM: "aoi_sel.custom"}

# Leaflet path options, and the VectorStyle field each one becomes
_LEAFLET_STYLE = {
    "color": "stroke",
    "fillColor": "fill",
    "fillOpacity": "fill_opacity",
    "weight": "width",
}


def _outline_style(map_style: Optional[dict]) -> VectorStyle:
    """The style of the AOI outline, from a Leaflet style dict or the default ``aoi.json``.

    The default colours follow the theme, so they stay unset and the map draws them in
    its primary colour. As in Leaflet, a fill is drawn unless ``fill`` is False, in
    ``color`` at an opacity of 0.2 unless ``fillColor`` and ``fillOpacity`` say
    otherwise; ``stroke: False`` hides the line. Other Leaflet options are dropped.
    """
    if map_style is None:
        style = json.loads((ss.JSON_DIR / "aoi.json").read_text())
        themed = {"color", "fillColor"}
    else:
        style, themed = map_style, set()
    given = {key: value for key, value in style.items() if key not in themed}
    fields = {field: given[key] for key, field in _LEAFLET_STYLE.items() if key in given}
    if style.get("fill") is False:
        fields.pop("fill", None)
        fields["fill_opacity"] = 0.0
    else:
        fields.setdefault("fill_opacity", 0.2)
        if "color" in given:
            fields.setdefault("fill", given["color"])
    if style.get("stroke") is False:
        fields["width"] = 0.0
    return VectorStyle(**fields)


def resolve_methods(
    methods: Union[str, List[str]] = "ALL",
    gee: bool = True,
    map_: Optional[sm.SepalMap] = None,
) -> Dict[str, Dict[str, str]]:
    """Return the methods a picker with these settings offers.

    Args:
        methods: 'ALL', 'ADMIN', 'CUSTOM', or a list of names to keep or, when each
            is prefixed with '-', to drop.
        gee: Whether Earth Engine is enabled. ASSET needs it.
        map_: The linked map. DRAW needs one with drawing tools (``map_.draw``).

    SHAPE and POINTS read the user's files: the local disk, or in a shared app
    the user's SEPAL workspace. A shared app without a session has neither and
    does not offer them.

    Returns:
        The enabled subset of :data:`METHODS`, keyed by method name.

    Raises:
        ValueError: If ``methods`` mixes added and removed names, or is not a
            recognised value.
    """
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
    if not isinstance(getattr(map_, "draw", None), Draw):
        method_dict.pop("DRAW", None)
    if not user_files_available():
        method_dict.pop("SHAPE", None)
        method_dict.pop("POINTS", None)

    return method_dict


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

    method_dict = resolve_methods(methods, gee, map_)

    # Build the item list with headers
    prev_type = None
    items = []
    for k, m in method_dict.items():
        current_type = m["type"]

        if prev_type != current_type:
            items.append({"type": "subheader", "title": msg(TYPE_LABEL_KEYS[current_type])})
        prev_type = current_type

        items.append({"title": msg(m["label_key"]), "value": k})

    # No method is "" here; a select counts "" as a pick and floats its label.
    with rv.Select(
        label=msg("aoi_sel.method"),
        items=items,
        v_model=reactive_value.value or None,
        on_v_model=lambda method: reactive_value.set(method or ""),
        density="compact",
        variant="underlined",
    ):
        pass


@solara.component_vue("SubmitOnEnter.vue")
def SubmitOnEnter(scope: str, event_submit: Optional[Callable[[Any], None]] = None):
    """Call ``event_submit`` when the user presses Enter in a field of the form.

    Args:
        scope: A class on the form that holds the fields and this component.
        event_submit: Called when Enter is pressed in a text field of the form,
            unless an open list takes the key to pick an item.
    """


@solara.component
@versionchanged(version="4.2", reason="Add countries and notify_success; Enter selects the AOI")
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
    spec: Union[AoiSpec, solara.Reactive[Optional[AoiSpec]], None] = None,
    on_spec: Optional[Callable[[Optional[AoiSpec]], None]] = None,
    autoselect: bool = True,
    countries: Optional[Collection[str]] = None,
    notify_success: bool = True,
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
        map_style: Custom style for AOI display on map, as Leaflet path options:
            ``color``, ``weight``, ``fillColor``, ``fillOpacity``, ``fill`` and
            ``stroke``. An Earth Engine AOI takes it as its visualization parameters.
        file_initial_folder: Initial folder for file-based method pickers (SHAPE, POINTS)
        clear_ref: Optional ref that receives a clear callback for external reset.
            The clear callback preserves the currently selected method so the
            user can retry without reselecting it.
        spec: The serializable record of a selection. This is the two-way state
            channel: set it to restore a picker, and read ``on_spec`` to persist
            what the user picked. Changing it restores again — no remount needed.
            Clearing the AOI publishes ``None`` here, so an app that persists this
            channel records the clear instead of resurrecting the old selection on
            the next load. Setting it to ``None`` from outside is a no-op rather
            than a clear — an empty spec and an untouched picker look the same, and
            ``clear_ref`` is the way to reset a picker that already holds one. A
            spec naming a method this picker does not offer (an ASSET spec with
            ``gee=False``, a DRAW spec with no map) is refused with a warning.
        on_spec: Callback when a selection succeeds, carrying its ``AoiSpec``.
        autoselect: Whether a restored spec is processed immediately, so ``value``
            holds a usable ``AoiResult`` and the map shows the AOI. Set False to
            fill the form and leave the run to the user.
        countries: The GAUL level-0 codes the admin methods offer. None offers every
            country. A restored admin spec in another country is refused with a
            warning.
        notify_success: Whether to announce a successful selection. Set False when
            the map already shows the AOI.

    Note:
        A restore is driven by three refs, because the picker's state lives in the
        widgets rather than in one object.

        ``applied_spec`` holds the last spec this component applied or published.
        An incoming spec that differs came from the app and is hydrated; one that
        matches is this component's own echo. Comparing rather than flagging also
        makes the effect idempotent under reacton's double effect-run.

        ``last_method`` holds the method the clear-on-change effect last saw.
        Hydration writes it before it moves the select, so a restore does not trip
        the clear it would otherwise look like.

        Pending processing is cancelled on restore, clear and unmount. ``alive``
        also guards publication during teardown, since the result belongs to the
        host application rather than to the task's internal state.

    Example:
        ```python
        @solara.component
        def MyApp():
            aoi = solara.use_reactive(None)

            # Ahead of the view: the bus exists only once the provider element
            # has rendered, so a consumer earlier in render order sees none.
            NotificationProvider()

            with solara.Column():
                AoiView(value=aoi, map_=my_map, gee=False)

                if aoi.value:
                    solara.Text(f"Selected: {aoi.value.name}")
        ```

        Feedback about the selection is published to the notification bus, not
        rendered inline -- the alerts further down this module are the fallback
        for an application that mounts no provider at all.

    Returns:
        None. AOI data is passed through value/on_value as AoiResult.
    """
    # Normalize value/loading to reactive
    reactive_value = solara.use_reactive(value, on_value)
    reactive_loading = solara.use_reactive(loading, on_loading)
    reactive_spec = solara.use_reactive(spec, on_spec)
    del value, on_value, loading, on_loading, spec, on_spec

    enabled_methods = resolve_methods(methods, gee, map_)

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
            # Before init_ee(): a connection with no session refuses here,
            # and a refusal must leave the global ee unbound.
            get_current_gee_interface()
            su.init_ee()
        return None

    solara.use_effect(_ensure_ee, [gee])

    # The map's drawing tools, if it has them
    aoi_draw = getattr(map_, "draw", None)
    if not isinstance(aoi_draw, Draw):
        aoi_draw = None
    token = solara.use_ref(object()).current

    selected_method = solara.use_reactive("")
    form_revision = solara.use_reactive(0)
    admin_codes = solara.use_reactive(())
    admin_code = solara.use_reactive(None)
    draw_name = solara.use_reactive("")
    shape_data = solara.use_reactive(None)
    points_data = solara.use_reactive(None)
    asset_data = solara.use_reactive(None)
    asset_loading = solara.use_reactive(False)
    # Bumped when the drawing changes, to render again; the fallback is a restored
    # drawing the tools could not take (a polygon with holes), kept for submit.
    draw_tick = solara.use_reactive(0)
    draw_fallback = solara.use_reactive(None)
    # The drawing session this view began; a newer session on the map ends it.
    draw_session = solara.use_ref(None)
    allowed_countries = None if countries is None else {str(code) for code in countries}

    # Restore and unmount bookkeeping; see Note in the docstring.
    applied_spec = solara.use_ref(None)
    last_method = solara.use_ref("")
    alive = solara.use_ref(True)
    # Raised by every run and every clear: a run whose number is no longer current
    # was cleared or replaced, and must not add or zoom.
    aoi_run = solara.use_ref(0)

    # Notification system (replaces embedded alert). When no
    # NotificationProvider is mounted, `notifications` is a NoopNotifier
    # and user feedback is published inline instead.
    notifications = use_notifications(required=False)
    fallback_message = solara.use_reactive("")
    fallback_level = solara.use_reactive("info")

    def _clear_map_layers(*, force: bool = False):
        store = getattr(map_, "layer_store", None) if map_ else None
        if store is None:
            return
        # The ids are shared by every AoiView of the store: only the one that drew the
        # outline removes it, unless it is about to draw another.
        if not force and _OUTLINE_OWNERS.get(store) is not token:
            return
        _OUTLINE_OWNERS.pop(store, None)
        # By id, not name: a vector AOI is named after its file. Removing a reserved id
        # also cancels the Earth Engine add still preparing it.
        for layer_id in (AOI_LAYER_ID, AOI_PREVIEW_LAYER_ID):
            store.remove(layer_id, missing_ok=True)

    def on_user_edit(_collection):
        draw_fallback.set(None)

    def _owns_draw() -> bool:
        session = draw_session.current
        return session is not None and session.active

    def _take_draw(features=None):
        draw_session.current = aoi_draw.begin(
            _DRAW_MODES, features=features, on_change=on_user_edit
        )
        # The traits the begin wrote rendered this view before it held the session.
        draw_tick.set(draw_tick.peek() + 1)

    def _sync_draw_control(active_method: str = "", *, retry: bool = False):
        """Hold a drawing session for DRAW, and end it for any other method.

        ``retry``: DRAW stays selected, so the session goes on and is only cleared.
        """
        if aoi_draw is None:
            return
        try:
            if active_method == "DRAW":
                if not retry:
                    _take_draw()
                elif _owns_draw():
                    draw_session.current.clear()
            elif draw_session.current is not None:
                # A session a newer one ended stays ended: this leaves the newer one be.
                draw_session.current.end()
                draw_session.current = None
        except Exception:
            log.exception("The drawing tools could not be synced")

    def _effective_drawing() -> dict:
        """The drawing this view may submit: nothing unless it holds the tools."""
        if not _owns_draw():
            return {"type": "FeatureCollection", "features": []}
        return draw_fallback.value or draw_session.current.features

    def _cancel_pending_run():
        """Stop a run in flight, unless the run itself is what asked.

        ``cancel()`` raises ``_CancelledErrorInOurTask`` when it is called from
        inside the task's own coroutine, and it can be: writing a reactive from the
        task body renders synchronously, so an effect that clears or restores runs
        on that same stack.
        """
        if task.pending and not task.is_current():
            task.cancel()

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
        aoi_run.current += 1
        _cancel_pending_run()
        if reset_loading:
            reactive_loading.set(False)

        if clear_value:
            reactive_value.set(None)
            # Retract the published spec too, or an app persisting through on_spec
            # still holds the cleared AOI and resurrects it on the next load.
            applied_spec.current = None
            reactive_spec.set(None)
        admin_codes.set(())
        admin_code.set(None)
        draw_name.set("")
        shape_data.set(None)
        points_data.set(None)
        asset_data.set(None)
        fallback_message.set("")
        fallback_level.set("info")

        draw_fallback.set(None)
        _clear_map_layers()
        if active_method is not None:
            _sync_draw_control(active_method)
        elif reset_method:
            _sync_draw_control("")
        else:
            _sync_draw_control(selected_method.value, retry=True)

        if reset_method:
            selected_method.set("")

    # Register clear callback for external use
    def _register_clear():
        if clear_ref is not None:

            def clear():
                # Preserve the currently selected method so the user can retry
                # immediately after clearing the previous AOI.
                _clear_current_aoi()
                # An incomplete draft may already publish None, so reset its local state too.
                form_revision.set(form_revision.peek() + 1)

            clear_ref.current = clear

    solara.use_effect(_register_clear, [map_ if map_ else None, aoi_draw])

    # Track the current task in the notification system
    task_tracker_ref = solara.use_ref(None)

    async def process_aoi() -> Optional[AoiResult]:
        """Process the selected AOI."""
        method = selected_method.value
        aoi_run.current += 1
        run = aoi_run.current

        def current() -> bool:
            return alive.current and aoi_run.current == run

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
                    admin_codes=admin_codes.value,
                )

            elif method == "DRAW":
                if aoi_draw is None:
                    raise ValueError(msg("aoi_sel.exception.no_draw_control"))

                features = _effective_drawing()
                if not features.get("features"):
                    raise ValueError("No drawn features found. Please draw an area on the map.")

                tracker.step("Processing drawn features...")
                result = process_draw(
                    geo_json=features,
                    name=draw_name.value,
                    gee=gee,
                    gee_interface=gee_interface,
                )

            elif method == "SHAPE":
                if not shape_data.value or not shape_data.value.get("pathname"):
                    raise ValueError("Please select a vector file")

                tracker.step("Processing vector file...")
                result = await process_shape(
                    **shape_data.value, gee=gee, gee_interface=gee_interface
                )

            elif method == "POINTS":
                if not points_data.value or not points_data.value.get("pathname"):
                    raise ValueError("Please select a points file and id/lat/lng columns")

                tracker.step("Processing points file...")
                result = await process_points(
                    **points_data.value, gee=gee, gee_interface=gee_interface
                )

            elif method == "ASSET":
                if not asset_data.value or not asset_data.value.get("asset_id"):
                    raise ValueError("Please select a GEE asset")

                tracker.step("Processing GEE asset...")
                result = await process_asset(
                    asset_id=asset_data.value["asset_id"],
                    asset_type=asset_data.value["type"],
                    column=asset_data.value.get("column", "ALL"),
                    value=asset_data.value.get("value"),
                    gee_interface=gee_interface,
                )

            else:
                raise ValueError("Please select a method")

            # Update the map if available
            if current() and map_ and result:
                tracker.step("Updating map...")

                _clear_map_layers(force=True)
                _OUTLINE_OWNERS[map_.layer_store] = token

                # Add the new AOI, in the overlay zone of the map's store
                if gee and result.feature_collection:
                    # A clear removes the reserved id, so a late add commits nothing,
                    # and the map supersedes its zoom.
                    await map_.add_ee_layer_async(
                        result.feature_collection,
                        map_style or {},
                        "aoi",
                        key=AOI_LAYER_ID,
                        autocenter=True,
                        overlay=True,
                        attribution=(
                            f"Google Earth Engine, {admin_source_attribution(gee=True)}"
                            if result.admin is not None
                            else "Google Earth Engine"
                        ),
                    )
                elif result.admin is not None:
                    level = int(method[-1])
                    preview = create_wms_preview_layer(
                        level=level,
                        admin_code=result.admin,
                        name="aoi",
                        attribution=admin_source_attribution(gee=False),
                    )
                    map_.layer_store.add(preview, replace=True)

                    # tiles have no bounds
                    bounds = await fetch_admin_bounds_async(level=level, admin_code=result.admin)
                    if current():
                        map_.zoom_bounds(bounds)
                elif result.gdf is not None:
                    # a plain GeoDataFrame: pygadm's subclass
                    # fails in the frames geopandas builds from it
                    gdf = gpd.GeoDataFrame(result.gdf).to_crs(4326)
                    outline = LayerSpec.from_geojson(
                        gdf,
                        id=AOI_LAYER_ID,
                        name=result.name,
                        zone="overlay",
                        style=_outline_style(map_style),
                    )
                    map_.layer_store.add(outline, replace=True)
                    map_.zoom_bounds(gdf.total_bounds)

            if not alive.current:
                tracker.complete()
                return None

            tracker.complete()
            return result

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
            if task.value is not None and alive.current:
                result = task.value
                applied_spec.current = result.spec
                reactive_spec.set(result.spec)
                reactive_value.set(result)
                if notify_success and has_notifications:
                    notifications.success(msg("aoi_sel.complete"))
                elif notify_success:
                    fallback_message.set(msg("aoi_sel.complete"))
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

    def _seed_draw(geo_json):
        # The restored AOI stays editable. Tools that cannot take it (a polygon with
        # holes) begin empty, and the spec's GeoJSON stands in for it.
        if aoi_draw is None:
            return
        fallback = None
        try:
            try:
                _take_draw((geo_json or {}).get("features") or [])
            except ValueError:
                log.warning("The drawn AOI cannot be edited on the map", exc_info=True)
                fallback = geo_json
                _take_draw()
        except Exception:
            log.exception("The drawing tools could not be seeded")
        draw_fallback.set(fallback)

    def _apply_spec():
        incoming = reactive_spec.value
        if incoming is None or incoming == applied_spec.current:
            return
        if incoming.method not in enabled_methods:
            notifications.warning(
                f"Cannot restore a {incoming.method} AOI here: this picker does not "
                f"offer that method."
            )
            return
        if (
            allowed_countries is not None
            and incoming.method in ADMIN_METHODS
            and incoming.admin_codes
            and incoming.admin_codes[0] not in allowed_countries
        ):
            notifications.warning(
                f"Cannot restore {incoming.name or 'this AOI'} here: this picker does not "
                f"offer its country."
            )
            return
        applied_spec.current = incoming
        last_method.current = incoming.method

        _cancel_pending_run()
        if incoming.method not in (selected_method.value, "DRAW"):
            _sync_draw_control(incoming.method)

        selected_method.set(incoming.method)
        if incoming.method in ADMIN_METHODS:
            admin_codes.set(incoming.admin_codes)
            # Also set the leaf directly. The selector derives admin_code from the
            # cascade in an effect, and with autoselect on the task starts in this
            # same pass — waiting on that effect would make the run depend on
            # scheduling order rather than on anything guaranteed.
            admin_code.set(incoming.admin_codes[-1] if incoming.admin_codes else None)
        elif incoming.method == "SHAPE":
            shape_data.set(incoming.shape_data())
        elif incoming.method == "POINTS":
            points_data.set(incoming.points_data())
        elif incoming.method == "ASSET":
            asset_data.set(incoming.asset_data())
        elif incoming.method == "DRAW":
            draw_name.set(incoming.name or "")
            _seed_draw(incoming.geo_json)

        if autoselect:
            start_process()

    solara.use_effect(_apply_spec, [reactive_spec.value])

    # Handle method changes
    def on_method_change():
        if selected_method.value == last_method.current:
            return
        last_method.current = selected_method.value
        if selected_method.value:
            _clear_current_aoi(active_method=selected_method.value)

    solara.use_effect(on_method_change, [selected_method.value])

    # Cleanup on unmount
    def _cleanup():
        # Re-arm on every run. The effect's dep is the map identity, so a map swap
        # runs the previous cleanup — which sets this False — and then re-runs this
        # body. Without re-arming, one map change would silently mute every later
        # publish and leave the picker looking dead.
        alive.current = True

        def cleanup():
            alive.current = False

            # Release only what this picker owns. `value` belongs to the caller —
            # use_reactive passes a host-owned reactive straight through — and
            # unmounting the widget is not the user dropping their AOI.
            _clear_current_aoi(active_method="", reset_loading=True, clear_value=False)

            # Note: We intentionally do NOT reset map center/zoom on unmount
            # to avoid surprising side effects for host apps that own the map state

        return cleanup

    solara.use_effect(_cleanup, [map_ if map_ else None])

    def _watch_drawing():
        if aoi_draw is None:
            return None

        def on_change(_change=None):
            draw_tick.set(draw_tick.peek() + 1)

        # After a map swap the new tools are taken here; the cleanup above ended the old.
        if selected_method.peek() == "DRAW" and not _owns_draw():
            try:
                _take_draw()
            except Exception:
                log.exception("The drawing tools could not be taken")
        map_.observe(on_change, names=["drawn", "draw_request"])
        on_change()

        def stop():
            map_.unobserve(on_change, names=["drawn", "draw_request"])

        return stop

    solara.use_effect(_watch_drawing, [aoi_draw if aoi_draw else None])

    draw_tick.value  # read, so a change of the drawing renders again
    # The selectors publish None until their form is complete.
    method = selected_method.value
    selections = {"SHAPE": shape_data, "POINTS": points_data, "ASSET": asset_data}
    if method in ADMIN_METHODS:
        form_complete = bool(admin_code.value)
    elif method == "DRAW":
        form_complete = bool(_effective_drawing()["features"])
    else:
        form_complete = method in selections and bool(selections[method].value)

    # Prepare task button props (called unconditionally to satisfy hooks validator)
    btn_props = use_task_button(task, on_start=start_process)

    def _submit_on_enter(_data=None):
        if form_complete and not task.pending and not asset_loading.value:
            start_process()

    # Render
    with solara.Column(classes=["mx-0", "px-0", "sepal-aoi-view"]).key(str(form_revision.value)):
        SubmitOnEnter(scope="sepal-aoi-view", event_submit=_submit_on_enter)

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
                codes=admin_codes,
                countries=countries,
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
            if aoi_draw is not None:
                with rv.TextField(
                    label=msg("aoi_sel.aoi_name"),
                    v_model=draw_name.value,
                    on_v_model=draw_name.set,
                    variant="outlined",
                    density="compact",
                ):
                    pass
            else:
                solara.Error(msg("aoi_sel.exception.no_draw_control"))

        elif selected_method.value == "ASSET" and gee:
            session_gee_interface = get_current_gee_interface()
            AssetSelectComponent(
                gee_interface=session_gee_interface,
                value=asset_data,
                loading=asset_loading,
            )

        # Action buttons
        TaskButtonComponent(
            label=msg("aoi_sel.btn"),
            **btn_props,
            external_busy=asset_loading.value or not form_complete,
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
