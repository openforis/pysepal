"""Removed in pysepal 5.0: the ipyleaflet zoom control.

Kept as a stub so that an app still importing it gets a message saying what to
do instead of a bare ``ModuleNotFoundError``.
"""

raise ImportError(
    "pysepal.mapping.zoom_control was removed in pysepal 5.0. The map draws its own zoom, scale and fullscreen controls; pin "
    '"pysepal<5" for an app that still uses it. See https://github.com/openforis/'
    "pysepal/blob/main/docs/guides/migrating-to-pysepal-5.md"
)
