"""Removed in pysepal 5.0: the ipyvuetify 1 layer control.

Kept as a stub so that an app still importing it gets a message saying what to
do instead of a bare ``ModuleNotFoundError``.
"""

raise ImportError(
    "pysepal.mapping.layers_control was removed in pysepal 5.0. SepalMap keeps its layers in "
    "SepalMap.layer_store, which the Solara LayerPanel lists and edits; pin "
    '"pysepal<5" for an app that still uses LayersControl. See https://github.com/openforis/'
    "pysepal/blob/main/docs/guides/migrating-to-pysepal-5.md"
)
