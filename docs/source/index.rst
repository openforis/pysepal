.. image:: https://raw.githubusercontent.com/openforis/sepal-doc/master/docs/source/_images/sepal_header.png

pysepal
-------

.. note::

    `sepal-ui` has been renamed to `pysepal`. pysepal 4.0 removed the ``sepal_ui``
    compatibility package: ``import sepal_ui`` no longer works, use ``import pysepal``.
    See ``docs/guides/migration-v4.md`` for the full 4.0 migration guide.

.. note::

    pysepal 5 needs ipyvuetify 3 and removed the ipyvuetify 1 widgets (``pysepal.sepalwidgets``
    and the widgets built on it). Their pages are being rewritten for the Solara components.
    Until then, read the `guides <https://github.com/openforis/pysepal/tree/main/docs/guides>`__
    and the `migration note <https://github.com/openforis/pysepal/blob/main/docs/guides/migrating-to-pysepal-5.md>`__.

--------------------------------------------------------------------------------

Currently translated in the following languages:

.. csv-table::

    English, Français, Español, 中国人

You can contribute to the translation effort on our `crowdin project <https://crowdin.com/project/sepal-ui>`__.

--------------------------------------------------------------------------------

:code:`pysepal` is a lib designed to create elegant python based dashboard in the SEPAL environment. It is designed on top of the amazing `Solara <https://solara.dev/>`_ and `ipyvuetify <https://ipyvuetify.readthedocs.io/en/latest/introduction.html>`_ libraries and will help developer to easily create interface for their workflows.
By using this libraries, you'll ensure a robust and unified interface for your scripts and a easy and complete integration into the SEPAL dashboard of application.

Working demo apps live in the `demo_apps <https://github.com/openforis/pysepal/tree/main/demo_apps>`__ folder of the repository.

We are happy to receive feedback and we welcome any kind of contribution.

.. image:: https://raw.githubusercontent.com/openforis/pysepal/main/docs/source/_image/sepal_ui_demo.gif

Contribute
----------

If you want to contribute you can fork the project in you own repository and then use it.
If you consider working with us, please follow the :doc:`contributing guidelines <./start/contribute>`.

Meet our :doc:`contributor <./start/authors>`.

.. toctree::
    :maxdepth: 1
    :hidden:

    start/index
    tutorials/index
    API Content <modules/pysepal>
    cli/index
