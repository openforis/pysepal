.. image:: https://raw.githubusercontent.com/openforis/sepal-doc/master/docs/source/_images/sepal_header.png

pysepal
-------

.. note::

    `sepal-ui` has been renamed to `pysepal`. pysepal 4.0 removed the ``sepal_ui``
    compatibility package: ``import sepal_ui`` no longer works, use ``import pysepal``.

.. image:: https://img.shields.io/badge/License-MIT-yellow.svg?logo=opensourceinitiative&logoColor=white
    :target: https://opensource.org/licenses/MIT
    :alt: License: MIT

.. image:: https://img.shields.io/badge/code%20style-black-000000.svg
   :target: https://github.com/psf/black
   :alt: Black badge

.. image:: https://img.shields.io/badge/code_style-prettier-ff69b4.svg?logo=prettier&logoColor=white
   :target: https://github.com/prettier/prettier
   :alt: prettier badge

.. image:: https://img.shields.io/badge/Conventional%20Commits-1.0.0-yellow.svg?logo=git&logoColor=white
   :target: https://conventionalcommits.org
   :alt: conventional commit

.. image:: https://img.shields.io/badge/DOI-10.5281%2Fzenodo.6467834-blue?logo=doi&logoColor=white
   :target: https://doi.org/10.5281/zenodo.6467834
   :alt: Citation

.. image:: https://img.shields.io/readthedocs/pysepal?logo=readthedocs&logoColor=white
    :target: https://pysepal.readthedocs.io/en/latest/
    :alt: Documentation Status

.. image:: https://img.shields.io/pypi/v/pysepal?color=orange&logo=pypi&logoColor=white
    :target: https://pypi.org/project/pysepal/
    :alt: PyPI version

.. image:: https://img.shields.io/conda/vn/conda-forge/pysepal?color=orange&logo=anaconda&logoColor=white
    :target: https://anaconda.org/conda-forge/pysepal
    :alt: Conda Version

.. image:: https://img.shields.io/pypi/pyversions/pysepal?color=orange&logo=python&logoColor=white
   :target: https://pypi.org/project/pysepal/
   :alt: supported Python version

.. image:: https://img.shields.io/github/actions/workflow/status/openforis/pysepal/unit.yml?logo=github&logoColor=white
    :target: https://github.com/openforis/pysepal/actions/workflows/unit.yml
    :alt: build

--------------------------------------------------------------------------------

Currently translated in the following languages:

.. list-table::

   * - English
     - Français
     - Español
     - 中国人
   * - .. image:: https://img.shields.io/static/v1?label=en&message=100%&logo=crowdin&logoColor=white&color=blue
     - .. image:: https://img.shields.io/badge/dynamic/json?label=fr&logo=crowdin&logoColor=white&query=%24.progress.2.data.translationProgress&url=https%3A%2F%2Fbadges.awesome-crowdin.com%2Fstats-15167678-506362.json
     - .. image:: https://img.shields.io/badge/dynamic/json?logoColor=white&label=es-ES&logo=crowdin&query=%24.progress.1.data.translationProgress&url=https%3A%2F%2Fbadges.awesome-crowdin.com%2Fstats-15167678-506362.json
     - .. image:: https://img.shields.io/badge/dynamic/json?label=zh-CN&logo=crowdin&logoColor=white&query=%24.progress.5.data.translationProgress&url=https%3A%2F%2Fbadges.awesome-crowdin.com%2Fstats-15167678-506362.json

You can contribute to the translation effort on our `crowdin project <https://crowdin.com/project/sepal-ui>`__.

--------------------------------------------------------------------------------

:code:`pysepal` is a UI toolkit for building `ipyvuetify <https://ipyvuetify.readthedocs.io/en/latest/introduction.html>`_ and `Solara <https://solara.dev/>`_ dashboards, with first-class integration for the `SEPAL platform <https://sepal.io/>`__. It ships components for mapping (`ipyleaflet <https://ipyleaflet.readthedocs.io/>`_), AOI selection, Google Earth Engine session handling, notifications, exports, theming, and i18n — usable in any Jupyter or Solara context, and tightly wired into SEPAL when you run there.

The full documentation is available `here <https://pysepal.readthedocs.io/en/latest/>`__. Working demo apps live in `demo_apps/ <demo_apps>`__ and run under both Solara and Voila:

.. code-block:: bash

    ./run_solara.sh demo_apps/gallery.py --port 8901

We are happy to receive feedback and we welcome any kind of contribution.

.. list-table::
   :widths: 50 50

   * - |ndvi|
     - |radar|
   * - Sentinel-2 NDVI in the map demo, with its gradient legend, in the light and dark themes.
     - Sentinel-1 VV / VH / VV−VH composite over the river confluence at Manaus.

.. |ndvi| image:: https://raw.githubusercontent.com/openforis/pysepal/main/docs/source/_image/readme-map-app-ndvi.jpg
    :width: 100%
    :alt: Sentinel-2 NDVI in the map demo, light and dark theme

.. |radar| image:: https://raw.githubusercontent.com/openforis/pysepal/main/docs/source/_image/readme-map-app-radar.jpg
    :width: 100%
    :alt: Sentinel-1 radar composite in the map demo, light and dark theme

Contribute
----------

If you want to contribute you can fork the project in you own repository and then use it.
If you consider working with us, please follow the `contributing guidelines <CONTRIBUTING.rst>`__.

Meet our `contributor <AUTHORS.rst>`__.
