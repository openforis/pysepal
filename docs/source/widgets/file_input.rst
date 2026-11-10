File input
==========

Overview
--------

:code:`FileInput` is a field widget to search for files in the SEPAL folders. it inherits from the :code:`SepalWidget` class.
Any argument from the original :code:`Layout` ipyvuetify class can be used to complement it.

.. jupyter-execute::
    :raises:
    :stderr:

    from pysepal import sepalwidgets as sw

    # correct colors for the documentation
    # set to dark in SEPAL by default
    import ipyvuetify as v
    v.theme.dark = False

    file_input = sw.FileInput()
    file_input

the value can be retrieve from the :code:`v_model` trait.

Several files
-------------

With :code:`multiple=True` the value is a list of paths. A click on a file adds it to the selection or removes it, and a click on a folder opens it. The selection stays when the user opens another folder, so one selection can hold files from several folders. The field shows the number of selected files; click it to see the paths and remove one. The clear button removes all of them.

Every path in the list must be inside :code:`root`, as in single mode. The widget removes a path that is not.

.. jupyter-execute::
    :raises:
    :stderr:

    from pysepal import sepalwidgets as sw

    # correct colors for the documentation
    # set to dark in SEPAL by default
    import ipyvuetify as v
    v.theme.dark = False

    file_input = sw.FileInput(multiple=True, extensions=[".csv"])
    file_input

In a Solara app, give :code:`multiple=True` to :code:`FileInputComponent`. Its :code:`value` and :code:`on_value` then use :code:`list[str]`:

.. code-block:: python

    import solara

    from pysepal.solara.components.inputs.file_input import FileInputComponent

    tables = solara.reactive([])

    @solara.component
    def Page():
        FileInputComponent(multiple=True, extensions=[".csv"], value=tables)
        solara.Text(f"{len(tables.value)} tables selected")

Methods
-------

select_file
^^^^^^^^^^^

Manually select a file from it's path. No verification on the extension is performed. With :code:`multiple=True` the file is added to the selection.

.. jupyter-execute::
    :raises:
    :stderr:

    from pysepal import sepalwidgets as sw
    from pathlib import Path

    # correct colors for the documentation
    # set to dark in SEPAL by default
    import ipyvuetify as v
    v.theme.dark = False

    path = Path.home()/'test.txt'
    path.write_text("hello world")

    file_input = sw.FileInput()
    file_input.select_file(path)
    file_input

reset
^^^^^


Clear the File selection (all the files with :code:`multiple=True`) and move to the root folder if something was selected.

.. jupyter-execute::
    :raises:
    :stderr:

    from pysepal import sepalwidgets as sw
    from pathlib import Path

    # correct colors for the documentation
    # set to dark in SEPAL by default
    import ipyvuetify as v
    v.theme.dark = False

    path = Path.home()/'test.txt'
    path.write_text("hello world")

    file_input = sw.FileInput()
    file_input.select_file(path)
    file_input.reset()
    file_input

.. note::

    More information can be found `here <../modules/pysepal.sepalwidgets.html#pysepal.sepalwidgets.inputs.FileInput>`__.
