How to add a tile to the UI ?
=============================

let's assume that you have a new tile that you want to display in the UI to process geospatial data.

the tile cod is the following :

.. code-block:: python

    # component/tile/my_tile.py

    import time

    from pysepal import sepalwidgets as sw
    import ipyvuetify as v
    from component.message import msg
    from pysepal.scripts import utils as su
    from pysepal.scripts import decorator as sd

    class MyTile(sw.Tile):

        def __init__(self, model, **kwargs):

        # gather models
        self.model = model

        # a single widget
        self.slider = v.Slider(
            label       = msg("my_tile_slider"),
            class_      = "mt-5",
            thumb_label = True,
            v_model     = 0
        )

        self.model.bind(self.slider, 'slider_value')

        # construct the Tile with the widget we have initialized
        super().__init__(
            id_    = "my_tile",
            title  = msg("my_tile.title"),
            inputs = [self.slider],
            btn    = sw.Btn(),
            alert  = sw.Alert()
        )

        # now that the Tile is created we can link it to a specific function
        self.btn.on_event('click', self._on_run)

    @sd.loading_button(debug=False)
    def _on_run(self, widget, data, event):

        time.sleep(5)

        self.alert.add_live_msg("I've waited for 5 good seconds...", "warning")

        return

Create a partial ui
-------------------

At the root of your repository create a notebook called :code:`[my process_name]_ui.ipynb`.
In this file will create the instance of the tile object that we created

by writing the following steps (each code block need to be written in a separate cell):

.. code-block:: python

    from component import io
    from component import tile


.. tip::

    add the debugging :code:`io` required for you tile to work in stand-alone. it will allow you to test your process only by launching this notebook

create the io

.. code-block:: python

    my_io = MyIo()

create the tile

.. code-block:: python

    my_tile = MyTile(io)

display your tile

.. code-block:: python

    my_tile

display your io

.. code-block:: python

    my_io.__dict__

Normally if you launch all the cell of the current notebook you should already see your tile. Clear all the cell.

Display in no_ui.ipynb
----------------------

in the gathering first cell

add an extra line with that will run the newly created partial ui notebook

.. code-block:: python

    # no_ui.ipynb

    %run my_tile_ui.ipynb
    [...]

and simply display the tiles in separate cells. they will of course be displayed in the order you write them

.. code-block:: python

    my_tile


Display in ui.ipynb
-------------------

same as in the :code:`no_ui.ipynb` notebook, add the extra line to run the newly created partial ui notebook
Then add the :code:`my_tile` variable in the app_content list.

in the :code:`app_items` list, add a :code:`DrawerItem` corresponding to your tile. To link it, use the 'id' attribute of your tile, here "my_tile"

.. code-block:: python

    # ui.ipynb

    app_items = [
        # [...]
        sw.DrawerItem(
            title = msg("app.drawer_item.aoi"),
            icon 'fa-solid fa-cogs',  # optional
            card="my_tile"
        )
    ]


start your voila dashboard "et voila!", you're tile will be loaded at the kernel start and display when you click on the corresponding drawer item.
