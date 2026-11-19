"""The ``ee`` object an export submits: SEPAL styling, then the selected bands."""

from __future__ import annotations

from pysepal.mapping.visualization import set_viz_params

from .models import ExportRequest


def with_viz_params(request: ExportRequest) -> object:
    """Return the export image with SEPAL visualization properties embedded.

    Apps that produce SEPAL-styled layers can pass ``vis_params`` on
    :class:`ResolvedExport` to keep the displayed styling on the exported asset.
    The properties are written via
    :func:`pysepal.mapping.visualization.set_viz_params` and survive on
    ``Export.image.toAsset`` outputs; Drive/SEPAL targets stage through a
    GeoTIFF where image properties become GDAL tags rather than EE properties,
    but applying them unconditionally is cheap and keeps downstream EE-asset
    consumers consistent.
    """
    if request.export_kind != "image" or not request.vis_params:
        return request.ee_object
    return set_viz_params(request.ee_object, **request.vis_params)


def select_bands(ee_object: object, request: ExportRequest) -> object:
    """Subset an image to the user-picked bands before export.

    Tables thread ``selectors`` directly through to the EE export call (where
    Earth Engine interprets them as feature property names). Images need an
    explicit ``image.select(...)`` because the image-export endpoints do not
    accept a selectors parameter — the band subset has to be baked into the
    image itself.
    """
    if request.export_kind != "image" or not request.selectors:
        return ee_object
    return ee_object.select(list(request.selectors))


def prepared_image(request: ExportRequest) -> object:
    """Return the image to export, styled and subset to the selected bands."""
    return select_bands(with_viz_params(request), request)


__all__ = ["prepared_image", "select_bands", "with_viz_params"]
