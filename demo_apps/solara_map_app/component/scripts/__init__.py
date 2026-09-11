"""Pure Python logic for the Solara map application.

Nothing in this package renders UI: it builds Earth Engine objects, reduces them
to legend numbers and declares what the export dialog may offer. Keeping it free
of Solara means it can be exercised without a kernel.
"""

from .exports import export_sources
from .legends import elevation_class_legend, gradient_legend, upsert_legends
from .processing import build_outputs, ndvi_composite

__all__ = [
    "build_outputs",
    "elevation_class_legend",
    "export_sources",
    "gradient_legend",
    "ndvi_composite",
    "upsert_legends",
]
