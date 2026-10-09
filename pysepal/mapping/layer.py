"""Customized ``Layer`` object containing EE metadata."""

from typing import Dict, Optional

import ee
from ipyleaflet import TileLayer


class EELayer(TileLayer):

    ee_object: Optional[ee.ComputedObject] = None
    "ee.object: the ee.object displayed on the map"

    theme_urls: Optional[Dict[bool, str]] = None
    "the tile url rendered for each theme, keyed by whether it is dark. ``SepalMap`` swaps ``url`` between them when its theme changes."

    def __init__(
        self,
        ee_object: ee.ComputedObject,
        theme_urls: Optional[Dict[bool, str]] = None,
        **kwargs,
    ) -> None:
        """Wrapper of the TileLayer class to add the ee object as a member.

        useful to get back the values for specific points in a v_inspector.

        Args:
            ee_object (ee.object): the ee.object displayed on the map
            theme_urls: the tile url rendered for each theme, keyed by whether it is dark. Earth Engine bakes the colours into the tiles, so a layer that follows the map theme needs one render per theme.
        """
        self.ee_object = ee_object
        self.theme_urls = theme_urls

        super().__init__(**kwargs)
