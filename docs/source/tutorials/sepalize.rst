How to sepalize a process
=========================

The wire-frame of your app is now ready but it's an empty shell and we would like to wire it to an actual process.
Sepalizing is a 2 step process that will be presented in this tutorial through the sepalization of a GEE process.

.. tip::

    If your workflow is using CLI or is already in python (notebook) you don't need to read the first section and can directly jump to "wire my process to a tile"

From GEE to Python
------------------

Most of the process that requires sepalization are based on Google Earth Engine (that we will call GEE). This processes are written in Javascript in the GEE console and execute in the Javascript environment of Google (which provide several embedded tools such as a map and a plotting tool).
Fortunately the Seapl framework can use the Earth Engine Python API so anything that exist in Javascript can be translated into python !

For this tutorial we will translate the following script. It analyses the cloud coverage on top of an selected AOI between 2 dates.
The script provide both images and plots. It is available `here <https://code.earthengine.google.com/8d5747ccd50da69aef3fa56d87fb626a>`__.

.. code-block:: javascript

    //###################################
    //##                               ##
    //##      get the parameters       ##
    //##                               ##
    //###################################

    var aoi = ee.FeatureCollection('users/bornToBeAlive/aoi_sandan')
    var point = ee.Geometry.Point(-2.927457,6.400793)
    var start_date = '2012-01-01'
    var end_date = '2015-12-31'

    //###################################
    //##                               ##
    //##      start of the script      ##
    //##                               ##
    //###################################

    // Import the Landsat 8 TOA image collection.
    // var l8 = ee.ImageCollection('LANDSAT/LC08/C01/T1_SR')
    var l8 = ee.ImageCollection('LANDSAT/LC08/C01/T1_TOA')
        .filterBounds(point)
        .filterDate('2012-01-01', '2015-12-31')
        .sort('CLOUD_COVER')
    ;

    // var l7 = ee.ImageCollection('LANDSAT/LE07/C01/T1_SR')
    var l7 = ee.ImageCollection('LANDSAT/LE07/C01/T1_TOA')
        .filterBounds(point)
        .filterDate('2012-01-01', '2015-12-31')
        .sort('CLOUD_COVER')
    ;

    //cloud
    l8 = l8.map(ee.Algorithms.Landsat.simpleCloudScore)
    l7 = l7.map(ee.Algorithms.Landsat.simpleCloudScore)

    // add NDMI
    var addNDMI_l8 = function(image) {
        var ndmi = image.normalizedDifference(['B5', 'B6']).rename('NDMI');
        return image.addBands(ndmi.multiply(100));
    };

    var addNDMI_l7 = function(image) {
        var ndmi = image.normalizedDifference(['B4', 'B5']).rename('NDMI');
        return image.addBands(ndmi.multiply(100));
    };

    l8 =  l8.map(addNDMI_l8)
    l7 =  l7.map(addNDMI_l7)

    // Get some image do display
    var image_l8 = l8.first()
    var image_l7 = l7.first()

    //#######################################
    //##                                   ##
    //##      visualisation parameter      ##
    //##                                   ##
    //#######################################

    // vis param
    var rgbVis_l8 = {
        bands: ['B4', 'B3', 'B2'],
        min: 0.05,
        max: 0.4,
        gamma: 1.1
    };

    var rgbVis_l7 = {
        bands: ['B3', 'B2', 'B1'],
        min: 0.05,
        max: 0.4,
        gamma: 1.1
    };

    var ndmiParams = {
        min: 0,
        max: 40,
        palette: ['blue', 'white', 'green']

    };

    var cloudParams = {
        min: 20,
        max: 80,
        palette: ['white', 'red']
    };

    //################################################################

    // Display the result.
    Map.addLayer(image_l8.select('cloud').clip(aoi), cloudParams, 'cloud L8');
    Map.addLayer(image_l7.select('cloud').clip(aoi), cloudParams, 'cloud L7');
    Map.addLayer(image_l8.clip(aoi), rgbVis_l8, 'RGB image L8');
    Map.addLayer(image_l7.clip(aoi), rgbVis_l7, 'RGB image L7');
    Map.addLayer(image_l8.select('NDMI').clip(aoi), ndmiParams, 'NDMI image L8');
    Map.addLayer(image_l7.select('NDMI').clip(aoi), ndmiParams, 'NDMI image L7');

    Map.centerObject(aoi)

    //###############################################################
    // use the first results images to place your point on the map
    // relaunch the script

    // Define a region of interest as a buffer around a point.
    var buffer = point.buffer(30);
    Map.addLayer(point, {color: 'red'}, 'buffer')

    // timeseries comparison
    print(ui.Chart.image.series(l8.select(['cloud', 'NDMI']), buffer, ee.Reducer.mean(), 30));
    print(ui.Chart.image.series(l7.select(['cloud', 'NDMI']), buffer, ee.Reducer.mean(), 30));

Set up
^^^^^^

create a test.ipynb notebook at the root of your repository. This notebook will have access to all the app component which will fasten the app wiring.

in this file create a first cell where you initialize EE API :

.. code-block:: python

    # test.ipynb

    import ee

    ee.Initialize()

.. danger::

    If you did not authenticate to Google Earth Engine previously, some extra action will be asked in the cell output. This process need to be done at least once


Define the model
^^^^^^^^^^^^^^^^

Then you need to identify what are the input and the output of your process in order to create a model.
Here we have 3 input :

- AOI
- start_date
- end_date
- point coordinates

And 2 output:
- l8 ImageCollection
- l7 ImageCollection

We will thus create a :code:`model` that matches our process requirements. For more information please refer to this `page <#>`_ of the documentation.

.. code-block: python

    # component/model/process_model.py

    from traitlets import Any
    from pysepal.model import Model

    class ProcessIo(Model):

        # inputs
        asset = Any(None).tag(sync=True) # ee.FeatureCollection
        start_date = Any(None).tag(sync=True) # str representing the start date in YYY-MM-DD format
        end_date = Any(None).tag(sync=True) # str representing the end date in YYY-MM-DD format
        point = Any(None).tag(sync=True) # ee.Point

        # output
        l8 = Any(None).tag(sync=True) # ee.ImageCollection
        L7 = Any(None).tag(sync=True) # ee.ImageCollection

.. tip::

    Don't forget to add the the file to the model package :code:`__init__.py` file

now in a second cell of our :code:`test.ipynb` we will initialize this io object with default parameters:

.. code-block:: python

    # test.ipynb

    from component import model

    process_model = model.ProcessModel()
    process_model.asset = ee.FeatureCollection('users/bornToBeAlive/Juaboso_Bia_HIA')
    process_model.start_date = '2012-01-01'
    process_model.end_date = '2015-12-31'

Get the FeatureCollections
^^^^^^^^^^^^^^^^^^^^^^^^^^

Now we want to get the images collection that will be used for the rest of the process. The translation from Javascript to Python is strait forward. Keep in mind that:

- Python doesn't use :code:`;` to end command but line break
- to keep the chaining behavior and readability of ee objects use :code:`\ ` at the end of your line
- :code:`and` and :code:`or` are protected in python, use :code:`And` and :code:`Or` instead

.. note::

    If you are experiencing difficulties in the translation of your code please ask questions on `GIS.stackexchange <https://gis.stackexchange.com>`_ using the :code:`python` and :code:`gee` keyword.

.. code-block:: python

    # test.ipynb

    # Import the Landsat 8 TOA image collection.
    l8 = ee.ImageCollection('LANDSAT/LC08/C01/T1_TOA') \
        .filterBounds(aoi) \
        .filterDate(process_model.start_date, process_model.end_date) \
        .sort('CLOUD_COVER') \

    l7 = ee.ImageCollection('LANDSAT/LE07/C01/T1_TOA') \
        .filterBounds(aoi) \
        .filterDate(process_model.start_date, process_model.end_date) \
        .sort('CLOUD_COVER') \

    # cloud
    l8 = l8.map(ee.Algorithms.Landsat.simpleCloudScore)
    l7 = l7.map(ee.Algorithms.Landsat.simpleCloudScore)

    # add NDMI
    def addNDMI_l8(image):
        ndmi = image.normalizedDifference(['B5', 'B6']).rename('NDMI')
        return image.addBands(ndmi.multiply(100))

    def addNDMI_l7(image):
        ndmi = image.normalizedDifference(['B4', 'B5']).rename('NDMI')
        return image.addBands(ndmi.multiply(100))

    process_io.l8 =  l8.map(addNDMI_l8)
    process_io.l7 =  l7.map(addNDMI_l7)


display the results on a map
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

to display our result we will use the :code:`SepalMap` class embedded in the pysepal :code:`mapping` package. It's a wrapper of `geemap` Map with additional useful function. A complete description can be found `here <../modules/pysepal.mapping.html#pysepal.mapping.sepalMap>`__.

At the bottom of the script you see some visualization parameters. These parameters needs to be set in the :code:`parameter` component.

.. code-block:: python

    # component/parameter/ee_viz.py

    rgbVis_l8 = {'bands': ['B4', 'B3', 'B2'], 'min': 0.05, 'max': 0.4, 'gamma': 1.1}
    rgbVis_l7 = {'bands': ['B3', 'B2', 'B1'], 'min': 0.05, 'max': 0.4, 'gamma': 1.1}
    ndmiParams = {'min': 0, 'max': 40, 'palette': ['blue', 'white', 'green']}
    cloudParams = {'min': 20, 'max': 80, 'palette': ['white', 'red']}

.. tip::

    The Python dictionaries keys need to be set between :code:`"`

set a SepalMap object and then add all the images you like using the same method as in Javascript:

.. code-block:: python

    # test.ipynb

    from component import parameter as cp
    from pysepal import mapping as sm

    Map = sm.SepalMap(['CartoDB.Positron'])

    Map.addLayer(process_model.l8.first().select('cloud').clip(process_model.asset), cloudParams, 'cloud L8')
    Map.addLayer(process_model.l7.first().select('cloud').clip(process_model.asset), cloudParams, 'cloud L7')
    Map.addLayer(process_model.l8.first().clip(process_model.asset), rgbVis_l8, 'RGB image L8')
    Map.addLayer(process_model.l7.first().clip(process_model.asset), rgbVis_l7, 'RGB image L7')
    Map.addLayer(process_model.l8.first().select('NDMI').clip(process_model.asset), ndmiParams, 'NDMI image L8')
    Map.addLayer(process_model.l7.first().select('NDMI').clip(process_model.asset), ndmiParams, 'NDMI image L7')

    Map.zoom_ee_object(process_model.asset.geometry())

Create the Histogram
^^^^^^^^^^^^^^^^^^^^

GEE provide tools to directly produce graphs out of ImageCollections. In Python, the graphs will be displayed using the :code:`pyplotlib` or the :code:`bqplot` libraries.
So our work here is to extract the data from our images to reproduce the behavior of the plotting function. In this script we will translate the :code:`ui.Chart.image.series` method but it can be any other one.

.. tip::

    You can ask help on `GIS.StackExchange <https://gis.stackexchange.com>`_ on the translation of the different charting methods. Some of them have already been treated:

    - `how to get the value from ui.Chart.image.series <https://gis.stackexchange.com/questions/385704/how-to-get-the-value-from-ui-chart-image-series>`_

We thus need to create a specific function that build a :code:`matplotlib` chart from ee data :

 .. code-block:: python

    # test.ipynb

    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    import pandas as pd

    from datetime import datetime
    from dateutil.relativedelta import *

    def create_hist(dataset, point, title):

        buffer = point.buffer(30)

        stats_image_collection = dataset.select(['cloud', 'NDMI']).map(lambda image:
            ee.Image(image.setMulti(image.reduceRegion(
                reducer = ee.Reducer.mean(),
                geometry = buffer,
                scale = 30,
                maxPixels = 1e9
            )))
        )

        dates = [datetime.fromtimestamp(d//1000) for d in stats_image_collection.aggregate_array('system:time_start').getInfo()]
        ndmi = stats_image_collection.aggregate_array('NDMI').getInfo()
        cloud = stats_image_collection.aggregate_array('cloud').getInfo()

        if len(ndmi) == len(cloud) == len(dates):
            pass
        elif len(dates) > len(cloud) == len(ndmi):
            dates = dates[1:]
        else:
            raise Exception(f'The size are all different.\n dates: {len(dates)}\n ndmi: {len(ndmi)}\n cloud: {len(cloud)}')

        df = pd.DataFrame({'ndmi': ndmi, 'cloud': cloud}, index = dates)

        years = mdates.YearLocator()   # every year
        months = mdates.MonthLocator()  # every month
        years_fmt = mdates.DateFormatter('%b-%y')

        fig, ax = plt.subplots(figsize=(10,10))
        df.plot(ax=ax)
        ax.set_title(title, fontweight="bold")

        # format the ticks
        ax.xaxis.set_major_locator(years)
        ax.xaxis.set_major_formatter(years_fmt)
        ax.xaxis.set_minor_locator(months)

        plt.show()

This function can then be called on each image from the :code:`process_model`:

.. code-block:: python

    # test.ipynb

    create_hist(process_model.l8, process_model.point, 'landsat 8')
    create_hist(process_model.l7, process_model.point, 'landsat 7')

All this functions are now functional. You can add them in the script component using the necessary parameters here :code:`process_model` and :code:`Map`.

wire process to a tile
----------------------

We will assume that you followed the tutorial on `how to add a tile to my module <#>`_ and that your logic is described in the scripts package.
If that's not the case please refer to the appropriate step of the documentation.

your tile should look like this one :

.. code-block:: python

    # component/tile/process_tile.py

    # component and widgets imports
    # [...]
    from component import scripts as cs

    class ProcessTile(sw.Tile):

        def __init__(self, model, aoi_model, m):

            # Define the model and the aoi_model as class attribute so that they can be manipulated in its custom methods
            self.model = model
            self.aoi_model = aoi_model
            semf.m = m

            # the widget are defined
            # [...]

            # and linked to the io attributes using the model
            # [...]

            # construct the Tile with the widget we have initialized
            super().__init__(
                id_    = "process_widget", # the id will be used to make the Tile appear and disappear
                title  = msg("process.title"), # the Title will be displayed on the top of the tile
                inputs = [...] # input list
                btn    = sw.Btn(),
                alert  = sw.Alert()
            )


We want to launch the process when the button is click and use all the model attributes as parameters. important things in your tile are:

- set the model objects as class attributes
- wire the widget to the model attributes
- create a button

:code:`btn` is a Vuetify widget so it inherit some Javascripts behaviors that are describe in the `ipyvuetify documentation <https://ipyvuetify.readthedocs.io/en/latest/>`_.
here we will launch a function on every click on it:

.. code-block:: python

    # component/tile/process_tile.py

    from pysepal.scripts.utils import loading_button

    class ProcessTile(sw.Tile):

        def __init__(self, io, aoi_io, m):

            #[...]
            # now that the Tile is created we can link it to a specific function
            self.btn.on_event("click", self._on_run)

    @loading_button()
    def _on_click(self, widget, data, event):
        # do stuff

        return self


Some explanation on what we just coded. The :code:`on_event` method is linking the button Javascripts behavior to the python function. a complete list of Javascript's events can be found `here <https://developer.mozilla.org/en-US/docs/Web/Events>`__.
this event is linked to a callback function. This function can only have 3 arguments :

- widget: the widget that thrown the event
- event: the details of the event
- data: the data shared on the event (none in most of the case)

As a member of the :code:`ProcessTile` class, the :code:`_on_click` method add the self argument in first position. It will allow the function to have access to all the class attribute.
A process should look like the following :

.. code-block:: python

    @loading_button()
    def _on_click(self, widget, event, data):

        # check that the input that you're gonna use are set (Not mandatory)
        if not self.output.check_input(self.aoi_io.get_aoi_name()): return
        if not self.output.check_input(self.io.year): return

        # do stuff

        return self
















