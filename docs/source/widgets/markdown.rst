Markdown
========

Overview
-------------

:code:`Markdown` is a widget to display `markdown <https://www.markdownguide.org/basic-syntax/>`_ flavored strings. it inherits from the :code:`SepalWidget` class.

.. jupyter-execute::
    :raises:
    :stderr:

    from pysepal import sepalwidgets as sw

    # correct colors for the documentation
    # set to dark in SEPAL by default
    import ipyvuetify as v
    v.theme.dark = False

    str_ = """
    **I am a title**
    I am some regular text
    """

    mkd = sw.Markdown(str_)
    mkd

.. warning::

    - No tabulation must be applied in the multi-line :code:`str`.
    - Don't forget to escape the "`" character, it will be interpreted as code mark

Change the text
---------------

:code:`mkd_str` is a trait: set it to display a new text. In a Solara component, :code:`sw.Markdown.element(mkd_str=...)` updates the same widget when the text changes, for example after a language change.

.. code-block:: python

    mkd = sw.Markdown("**I am a title**")
    mkd.mkd_str = "**I am a new title**"

Include multi-line markdown in the translation tool
---------------------------------------------------

If you want to use the translation tool AND create multi-line markdown text you should consider the following method

in :code:`en.json` use a list in your key with each element of the list corresponding to a line:

.. code-block:: json

    {
        "_comment": "component/message/en.json",
        "multiline_key": [
            "this is",
            " a multiline",
            "key"
        ]
    }

Then In your notebook you can call the key in a markdown widget and display it as multi-line text:

.. jupyter-execute::
    :raises:
    :stderr:

    from pysepal import sepalwidgets as sw

    # correct colors for the documentation
    # set to dark in SEPAL by default
    import ipyvuetify as v
    v.theme.dark = False

    multiline_key = [
        "this is",
        " a multiline",
        "key"
    ]

    mkd = sw.Markdown('  \n'.join(multiline_key))
    mkd

.. tip::

    line break in markdown need to be set with 2 blank space to be interpreted.

.. note::

    More information can be found `here <../modules/pysepal.sepalwidgets.html#pysepal.sepalwidgets.sepalwidget.Markdown>`__.
