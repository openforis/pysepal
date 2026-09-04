"""Solara components for Area of Interest (AOI) selection and management."""

from pysepal.solara.components.task_button import TaskButtonComponent, use_task_button

from .admin import fetch_admin_bounds_async, fetch_admin_items, process_admin
from .aoi_result import AoiResult
from .aoi_spec import AOI_SPEC_SCHEMA_VERSION, AoiSpec
from .aoi_view import AoiView, MethodSelect
from .constants import FAO_GAUL_LAYERS, FAO_WMS_BASE_URL, WMS_PREVIEW_LAYER_NAME
from .draw import process_draw
from .wms_utils import create_wms_preview_layer, remove_wms_preview_layer

__all__ = [
    # Core dataclass
    "AoiResult",
    "AoiSpec",
    "AOI_SPEC_SCHEMA_VERSION",
    # Admin functions
    "fetch_admin_items",
    "fetch_admin_bounds_async",
    "process_admin",
    # Draw functions
    "process_draw",
    # WMS utilities
    "create_wms_preview_layer",
    "remove_wms_preview_layer",
    "WMS_PREVIEW_LAYER_NAME",
    "FAO_WMS_BASE_URL",
    "FAO_GAUL_LAYERS",
    # UI components
    "AoiView",
    "MethodSelect",
    # Task button
    "TaskButtonComponent",
    "use_task_button",
]
