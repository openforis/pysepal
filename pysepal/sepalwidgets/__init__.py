"""All the widgets available in pysepal.

Package to access all the widgets available in pysepal. The widgets are all derived from ``IpyvuetifyWidget`` and ``SepalWidget``. They can be used to build interfaces in applications. ``pysepal.sepalwidgets`` includes all the widgets from ``ipyvuetify`` and some extra ones that are useful to build GIS related applications.

Everything module content can be called directly from the package.

.. deprecated:: 4.2.0
    ``pysepal.sepalwidgets`` needs ipyvuetify 1 (Vuetify 2) and will be removed in
    pysepal 5.0. Build the UI with the ``pysepal.solara`` components instead; see
    ``docs/guides/sepalwidgets-deprecation.md``.

Example:
    .. jupyter-execute::

        from pysepal import sepalwidgets as sw

        sw.Btn()
"""

import warnings

from pysepal._vuetify import IPYVUETIFY_V3

DEPRECATION_NOTE = (
    "https://github.com/openforis/pysepal/blob/main/docs/guides/sepalwidgets-deprecation.md"
)

if IPYVUETIFY_V3:
    raise ImportError(
        "pysepal.sepalwidgets supports ipyvuetify 1 only and is deprecated. Build the UI "
        'with pysepal.solara components, or pin "ipyvuetify<3" for an app that still uses '
        f"sepalwidgets. See {DEPRECATION_NOTE}"
    )

warnings.warn(
    "pysepal.sepalwidgets is deprecated since pysepal 4.2.0 and will be removed in 5.0: "
    "it needs ipyvuetify 1, whose Vuetify 2 reached its end of life. Build the UI with "
    f"pysepal.solara components. See {DEPRECATION_NOTE}",
    DeprecationWarning,
    stacklevel=2,
)

from pysepal.sepalwidgets.sepal_ipyvuetify import *  # noqa: E402, I

# import and/or overwrite with our customized widgets
from pysepal.sepalwidgets.sepalwidget import *
from pysepal.sepalwidgets.alert import *
from pysepal.sepalwidgets.app import *
from pysepal.sepalwidgets.btn import *
from pysepal.sepalwidgets.inputs import *
from pysepal.sepalwidgets.tile import *
from pysepal.sepalwidgets.widget import *
from pysepal.sepalwidgets.radio import *
