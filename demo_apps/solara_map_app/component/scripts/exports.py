"""Declare the datasets the export dialog is allowed to offer."""

from component.message import msg

from pysepal.solara.components.export import ExportSource, ResolvedExport


def export_sources(aoi_value, outputs) -> list[ExportSource]:
    """Declare what the export dialog is allowed to offer.

    The dialog only lists datasets a page explicitly registers here.
    """
    sources: list[ExportSource] = []

    if aoi_value is not None and aoi_value.feature_collection is not None:
        sources.append(
            ExportSource(
                id="selected_aoi",
                label=msg("export.aoi_label"),
                kind="table",
                description=msg("export.aoi_description"),
                resolve=lambda fc=aoi_value.feature_collection, name=aoi_value.name: ResolvedExport(
                    ee_object=fc,
                    default_name=name,
                    drive_folder="pysepal_exports",
                    sepal_folder="exports",
                ),
            )
        )

    if outputs is None:
        return sources

    def image_source(source_id, label, image, description, bands=None, default_bands=None):
        return ExportSource(
            id=source_id,
            label=label,
            kind="image",
            description=description,
            resolve=lambda: ResolvedExport(
                ee_object=image,
                default_name=f"{outputs.name_prefix}_{source_id}",
                region=outputs.region,
                default_scale=300,
                bands=bands,
                default_bands=default_bands,
                drive_folder="pysepal_exports",
                sepal_folder="exports",
            ),
        )

    sources += [
        image_source(
            "pixel_area",
            msg("layers.pixel_area"),
            outputs.pixel_area,
            msg("export.pixel_area_description"),
        ),
        image_source(
            "elevation_class",
            msg("layers.elevation"),
            outputs.elevation_class,
            msg("export.elevation_description"),
        ),
        image_source(
            "multi_band",
            msg("export.multi_band_label"),
            outputs.multi_band,
            msg("export.multi_band_description"),
            bands=("pixel_area_m2", "elevation_class", "flag"),
            # Pre-select the useful bands; `flag` stays deselectable from the dialog.
            default_bands=("pixel_area_m2", "elevation_class"),
        ),
    ]

    return sources
