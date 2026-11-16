"""Removed in pysepal 5.0: the ipyvuetify 1 widget layer.

Kept as a stub so that an app still importing it gets a message saying what to
do instead of a bare ``ModuleNotFoundError``.
"""

raise ImportError(
    "pysepal.sepalwidgets was removed in pysepal 5.0, which needs ipyvuetify 3. Build the "
    'UI with pysepal.solara components, or pin "pysepal<5" for an app that still uses '
    "sepalwidgets. See https://github.com/openforis/pysepal/blob/main/docs/guides/"
    "migrating-to-pysepal-5.md"
)
