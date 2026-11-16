"""Dialog step showing every way ``FileInputComponent`` selects paths.

Each variation sits above the exact value the app receives from it, so the
difference between a ``str`` and a ``list[str]`` value is visible as you click.
"""

from pathlib import Path
from typing import List, Union

import reacton.ipyvuetify as rv
import solara
from component.message import msg

from pysepal.solara.components.inputs import FileInputComponent

VECTOR_EXTENSIONS = [".geojson", ".gpkg", ".kml", ".shp"]
PRESET_FILES = ["demo_aoi.geojson", "demo_points.csv"]


def _variations(samples: str) -> tuple:
    """(catalogue key, initial value, FileInputComponent options) per input.

    The inputs open on the sample folder and the preset selects its files only
    when ``samples`` is set, i.e. when the user's files hold them.
    """
    preset = [str(Path(samples) / name) for name in PRESET_FILES] if samples else []
    # one level up, where there are folders to check
    parent = str(Path(samples).parent) if samples else ""
    return (
        ("single", "", {"initial_folder": samples}),
        ("multiple", [], {"multiple": True, "initial_folder": samples}),
        (
            "extensions",
            [],
            {"multiple": True, "extensions": VECTOR_EXTENSIONS, "initial_folder": samples},
        ),
        ("folders", [], {"multiple": True, "select_folders": True, "initial_folder": parent}),
        ("preset", preset, {"multiple": True, "initial_folder": samples}),
        ("no_clear", [], {"multiple": True, "clearable": False, "initial_folder": samples}),
    )


VALUE_STYLE = (
    "background: rgba(127, 127, 127, 0.12); border-radius: 4px; padding: 8px 12px;"
    " margin: 8px 0 0; font-size: 12px; white-space: pre-wrap; word-break: break-all;"
)


def _as_code(value: Union[str, List[str]]) -> str:
    """The value as the app sees it, one path per line for a list."""
    if isinstance(value, list) and value:
        return "[\n" + "".join(f"    {path!r},\n" for path in value) + "]"
    return repr(value)


@solara.component
def FileVariation(name: str, initial: Union[str, List[str]], options: dict):
    """One FileInputComponent configuration and the value it holds."""
    value = solara.use_reactive(initial)

    with rv.Html(tag="div", class_="mb-6"):
        rv.Html(
            tag="div",
            class_="text-subtitle-1 font-weight-medium",
            children=[msg(f"files.{name}.title")],
        )
        rv.Html(tag="div", class_="text-body-2 mb-2", children=[msg(f"files.{name}.description")])
        FileInputComponent(value=value, label=msg(f"files.{name}.label"), **options)
        rv.Html(tag="pre", style_=VALUE_STYLE, children=[_as_code(value.value)])


@solara.component
def FilesPanel(samples: str):
    """Every FileInputComponent selection mode, one under the other.

    Args:
        samples: The sample data folder, or ``""`` when the user's files do not
            hold it (see ``component.scripts.sample_folder``).
    """
    with rv.Html(tag="div", class_="pt-2"):
        rv.Html(tag="p", class_="text-body-2", children=[msg("files.intro")])
        for name, initial, options in _variations(samples):
            FileVariation(name=name, initial=initial, options=options).key(name)
