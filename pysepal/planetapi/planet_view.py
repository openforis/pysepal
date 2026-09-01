"""The ``Card`` widget to use in application to interface with Planet."""

from pathlib import Path
from typing import Optional

import ipyvuetify as v

import pysepal.sepalwidgets as sw
from pysepal.message import msg
from pysepal.planetapi.planet_model import PlanetModel
from pysepal.planetapi.planet_widgets import InfoView
from pysepal.scripts.decorator import loading_button


class PlanetView(sw.Layout):
    planet_model: Optional[PlanetModel] = None
    "Backend model to manipulate interface actions"

    btn: Optional[sw.Btn] = None
    "Button to trigger the validation process in the associated model"

    alert: Optional[sw.Alert] = None
    "Alert component to display end-user action results"

    info: bool = False
    "either to display or not a detailed description about the planet subscriptions"

    w_username: Optional[sw.TextField] = None
    "Widget to set credential username"

    w_password: Optional[sw.PasswordField] = None
    "Widget to set credential password"

    w_key: Optional[sw.PasswordField] = None
    "Widget to set credential API key"

    w_method: Optional[sw.Select] = None
    "Dropdown widget to select connection method"

    def __init__(
        self,
        btn: Optional[sw.Btn] = None,
        alert: Optional[sw.Alert] = None,
        planet_model: Optional[PlanetModel] = None,
        info: bool = False,
        **kwargs,
    ):
        """Stand-alone interface to capture planet lab credentials.

        It also validate its  subscription and connect to the client from_file in the model.

        Args:
            btn (sw.Btn, optional): Button to trigger the validation process in the associated model.
            alert (sw.Alert, v.Alert, optional): Alert component to display end-user action results.
            planet_model (pysepal.planetapi.PlanetModel): backend model to manipulate interface actions.
        """
        self.class_ = "d-block flex-wrap"

        super().__init__(**kwargs)

        self.planet_model = planet_model if planet_model else PlanetModel()
        self.btn = btn if btn else sw.Btn("Validate", small=True, class_="mr-1")
        self.alert = alert if alert else sw.Alert()

        self.w_username = sw.TextField(
            label=msg("planet.widget.username"), class_="mr-2", v_model=""
        )
        self.w_password = sw.PasswordField(label=msg("planet.widget.password"))
        self.w_key = sw.PasswordField(label=msg("planet.widget.apikey"), v_model="").hide()
        self.w_secret_file = sw.TextField(
            label=msg("planet.widget.store"),
            v_model=str(Path.home() / ".planet.json"),
            readonly=True,
            class_="mr-2",
        ).hide()
        self.w_info_view = InfoView(model=self.planet_model)

        self.w_method = v.Select(
            label=msg("planet.widget.method.label"),
            class_="mr-2",
            v_model="",
            items=[
                {"value": "from_file", "text": msg("planet.widget.method.from_file")},
                {"value": "credentials", "text": msg("planet.widget.method.credentials")},
                {"value": "api_key", "text": msg("planet.widget.method.api_key")},
            ],
        )

        self.w_store = sw.Checkbox(label=msg("planet.widget.store"), v_model=True)

        w_validation = v.Flex(
            style_="flex-grow: 0 !important;",
            children=[self.btn],
            class_="pr-1 flex-nowrap",
        )
        self.children = [
            self.w_method,
            sw.Layout(
                attributes={"id": "planet_credentials"},
                class_="align-center",
                children=[
                    self.w_username,
                    self.w_password,
                    self.w_key,
                    self.w_secret_file,
                ],
            ),
            self.w_store,
        ]

        if not btn:
            self.get_children(attr="id", value="planet_credentials")[0].set_children(
                w_validation, "last"
            )

        # Set it here to avoid displacements when using button
        self.set_children(self.w_info_view, "last")

        if not alert:
            self.set_children(self.alert, "last")

        self.w_method.observe(self._swap_inputs, "v_model")
        self.btn.on_event("click", self.validate)

        self.set_initial_method()

    def validate_secret_file(self) -> None:
        """Validate the secret file path."""
        if not Path(self.w_secret_file.v_model).exists():
            self.w_secret_file.error_messages = [msg("planet.exception.no_secret_file")]
            return False

        self.w_secret_file.error_messages = []
        return True

    def set_initial_method(self) -> None:
        """Set the initial method to connect to planet lab."""
        self.w_method.v_model = "from_file" if self.validate_secret_file() else "credentials"

    def reset(self) -> None:
        """Empty credentials fields and restart activation mode."""
        self.w_username.v_model = ""
        self.w_password.v_model = ""
        self.w_key.v_model = ""
        self.planet_model.__init__()

        return

    def _swap_inputs(self, change: dict) -> None:
        """Swap between credentials and api key inputs.

        Args:
            change.new: values of from_file, credentials, api_key
        """
        self.alert.reset()
        self.reset()

        # small detail, but validate the file every time the method is changed
        self.validate_secret_file()

        if change["new"] == "credentials":
            self.w_username.show()
            self.w_password.show()
            self.w_secret_file.hide()
            self.w_store.show()
            self.w_key.hide()

        elif change["new"] == "api_key":
            self.w_username.hide()
            self.w_password.hide()
            self.w_secret_file.hide()
            self.w_store.show()
            self.w_key.show()
        else:
            self.w_username.hide()
            self.w_password.hide()
            self.w_key.hide()
            self.w_store.hide()
            self.w_secret_file.show()

        return

    @loading_button()
    def validate(self, *args) -> None:
        """Initialize planet client and validate if is active."""
        self.planet_model.__init__()

        if self.w_method.v_model == "credentials":
            credentials = [self.w_username.v_model, self.w_password.v_model]

        elif self.w_method.v_model == "api_key":
            credentials = self.w_key.v_model

        else:
            if not self.validate_secret_file():
                raise Exception(msg("planet.exception.no_secret_file"))
            credentials = self.w_secret_file.v_model

        self.planet_model.init_session(credentials, write_secrets=self.w_store.v_model)

        # Check if the user has active subscriptions and show feedback
        if self.planet_model.authenticated:
            if self.planet_model.active:
                self.alert.add_msg(
                    "Successfully connected to Planet API with active subscriptions!",
                    type_="success",
                )
            else:
                self.alert.add_msg(
                    "Connected to Planet API but no active subscriptions found. Check the subscription list below.",
                    type_="warning",
                )

        return
