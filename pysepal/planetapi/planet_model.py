"""Model object dedicated to Planet interface."""

import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Union

import planet.data_filter as filters
import traitlets as t
from deprecated.sphinx import deprecated
from planet import DataClient
from planet.auth import Auth
from planet.exceptions import NoPermission
from planet.http import Session

from pysepal.message import msg
from pysepal.model import Model


class PlanetModel(Model):
    SUBS_URL: str = "https://api.planet.com/auth/v1/experimental/public/my/subscriptions"
    "The url of the planet API subscription"

    session: Optional[Session] = None
    "planet.http.session: planet session."

    subscriptions: t.Dict = t.Dict({}).tag(sync=True)
    "All the dictionary info from the available subscriptions"

    authenticated = t.Bool(False).tag(sync=True)
    "Value to determine if the credentials are valid and authentication was successful"

    active = t.Bool(False).tag(sync=True)
    "Value to determine if at least one subscription has the active true state"

    def _run_async(self, coro):
        """Run an async coroutine safely.

        This method handles running async code in both regular Python and
        environments with an already running event loop (like Jupyter/Voila).

        Args:
            coro: The coroutine to run

        Returns:
            The result of the coroutine
        """
        try:
            # Check if there's already a running loop (Jupyter/Voila)
            loop = asyncio.get_running_loop()
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()

        except RuntimeError:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            return loop.run_until_complete(coro)

    def __init__(self, credentials: Union[str, List[str]] = "") -> None:
        """Planet model helper to connect planet API client and perform requests.

        It can be
        instantiated whether itself or linked with a PlanetView input helper. All the methods
        are aimed to be used without the need of a view.

        Args:
            credentials: planet API key or tuple of username and password of planet explorer.
        """
        self.subscriptions = {}
        self.session = None
        self.authenticated = False
        self.active = False

        if credentials:
            self.init_session(credentials)

    @deprecated(
        version="3.0",
        reason="credentials member is deprecated, use self.auth._key instead",
    )
    def init_session(self, credentials: Union[str, List[str]], write_secrets: bool = False) -> None:
        """Initialize planet client with api key or credentials. It will handle errors.

        Args:
            credentials: planet API key, username and password pair or a secrets planet.json file.
            write_secrets: either to write the credentials in the secret file or not. Defaults to True.
        """
        if isinstance(credentials, str):
            credentials = [credentials]

        if not all(credentials):
            raise ValueError(msg("planet.exception.empty"))

        if len(credentials) == 2:
            self.auth = Auth.from_login(*credentials)

        # Check if the str is a path to a secret file
        elif len(credentials) == 1 and credentials[0].endswith(".json"):
            self.auth = Auth.from_file(credentials[0])

        else:
            self.auth = Auth.from_key(credentials[0])

        self.session = Session(auth=self.auth)
        self.authenticated = True
        self._is_active()

        if self.authenticated and write_secrets:
            Auth.store(self.auth)

        return

    def _is_active(self) -> None:
        """Check if the key has an associated active subscription and change the state button accordingly."""
        # As there is not any key that identify the nicfi contract,
        # let's find though all the subscriptions a representative name
        wildcards = ["Level_0", "Level_1", "Level2"]

        # get the subs from the api key and save them in the model. It will be useful
        # to avoid doing more calls.
        tmp_subscriptions: dict[str, list] = {"nicfi": [], "others": []}
        for sub in self.get_subscriptions():
            for w in wildcards:
                if w in str(sub):
                    tmp_subscriptions["nicfi"].append(sub)
                    break
            if sub not in tmp_subscriptions["nicfi"]:
                tmp_subscriptions["others"].append(sub)

        self.subscriptions = tmp_subscriptions

        states = self.search_status(self.subscriptions)
        self.active = any([next(iter(d.values())) for d in states])

        return

    def get_subscriptions(self) -> dict:
        """Load the user subscriptions.

        Returns:
            the dictionary of user subscription or empty list if nothing found
        """
        req = self.session.request("GET", self.SUBS_URL)

        try:
            response = self._run_async(req)

        except NoPermission:
            raise Exception(
                "You don't have permission to access to this resource. Check your input data."
            )

        except Exception as e:
            raise e

        return response.json() if response.status_code == 200 else {}

    def get_items(
        self,
        aoi: dict,
        start: Union[str, datetime],
        end: Union[str, datetime],
        cloud_cover: float,
        limit: int = 0,
    ) -> list:
        """Request imagery items from the planet API for the requested dates.

        Args:
            aoi: geojson clipping geometry
            start: the start of the request (YYYY-mm-dd))
            end: the end of the request (YYYY-mm-dd))
            cloud_cover: maximum cloud coverage.
            limit: number of items to constrain the search. Defaults to 0 to use all of them.

        Returns:
            items found using the search query

        """
        # cast start and end to str
        start = datetime.strptime(start, "%Y-%m-%d") if isinstance(start, str) else start
        end = datetime.strptime(end, "%Y-%m-%d") if isinstance(end, str) else end

        and_filter = filters.and_filter(
            [
                filters.geometry_filter(aoi),
                filters.range_filter("cloud_cover", lte=cloud_cover),
                filters.date_range_filter("acquired", gt=start),
                filters.date_range_filter("acquired", lt=end),
            ]
        )

        # PSScene3Band and PSScene4Band item type and assets are deprecated
        # since January 2023 so we are now only looking at PSScene
        item_types = ["PSScene"]

        async def _main():
            """Create an asyncrhonous function here to avoid making the main get_items as async.

            So we can keep calling get_items without any change.
            """
            client = DataClient(self.session)
            items = client.search(item_types, and_filter, name="quick_search", limit=limit)
            items_list = [item async for item in items]
            return items_list

        return self._run_async(_main())

    def get_mosaics(self) -> dict:
        """Get all the mosaics available in a client without pagination limitations.

        Returns:
            The mosaics contained in the API request.

        Note:
            The output format is the following:

            .. code-block:: json

                {
                    "_links": {
                        "_self": "<mosaic_url>",
                        "quads": "<quad_url>",
                        "tiles": "<xyz_tiles_url>"
                    },
                    "bbox": ["<4_corners_coordinates>"],
                    "coordinate_system": "<projection_system>",
                    "datatype": "uint16",
                    "first_acquired": "<date_of_aquisition>",
                    "grid": {
                        "quad_size": 4096,
                        "resolution": 4.77731426716
                    },
                    "id": "<mposaic_hashed_id>",
                    "interval": "<acquisition_interval>",
                    "item_types": ["<types_of_imagery"],
                    "last_acquired": "<last_image_timestamp>",
                    "level": "<max_zoom_level>",
                    "name": "<mosaic_name>",
                    "product_type": "timelapse",
                    "quad_download": true
                }
        """
        mosaics_url = "https://api.planet.com/basemaps/v1/mosaics"
        request = self.session.request("GET", mosaics_url)
        response = self._run_async(request)

        return response.json().get("mosaics", [])

    def get_quad(self, mosaic: dict, quad_id: str) -> dict:
        """Get a quad response for a specific mosaic and quad.

        Args:
            mosaic: A dict representing a mosaic in the format of list_mosaic
            quad_id: A quad id (typically <xcoord>-<ycoord>)

        Returns:
            The quad information as a dict.

        Note:
            The output format is the following:

            .. code-block:: json

                {
                    "_links": {
                        "_self": "<quad_url>",
                        "download": "<download_url>",
                        "items": "<items_url>",
                        "thumbnail": "<thumbnail_url>"
                    },
                    "bbox": ["<corner_coordinates>"],
                    "id": "<quad_id>",
                    "percent_covered": 100
                }
        """
        quads_url = "https://api.planet.com/basemaps/v1/mosaics/{}/quads/{}"
        quads_url = quads_url.format(mosaic["id"], quad_id)

        request = self.session.request("GET", quads_url)
        response = self._run_async(request)

        return response.json() or {}

    @staticmethod
    def search_status(d: dict) -> List[Dict[str, bool]]:
        """Get the status of a specific subscription.

        Args:
            d: dictionary of subscription object

        Returns:
            the (sub.name: status) pairs
        """
        states = []

        for v in d.values():
            for subs in v:
                if "plan" in subs:
                    plan = subs.get("plan")
                    state = True if plan.get("state") == "active" else False
                    states.append({plan.get("name"): state})

        return states
