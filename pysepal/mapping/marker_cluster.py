"""Removed in pysepal 5.0: the ipyleaflet marker cluster.

Kept as a stub so that an app still importing it gets a message saying what to
do instead of a bare ``ModuleNotFoundError``.
"""

raise ImportError(
    "pysepal.mapping.marker_cluster was removed in pysepal 5.0. Use LayerSpec.from_points(...) with VectorStyle(cluster=True); pin "
    '"pysepal<5" for an app that still uses it. See https://github.com/openforis/'
    "pysepal/blob/main/docs/guides/migrating-to-pysepal-5.md"
)
