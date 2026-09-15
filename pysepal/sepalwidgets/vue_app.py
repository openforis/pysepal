"""Custom Map app layout for SEPAL ui Map interfaces."""

import logging
from pathlib import Path
from typing import Iterable, Optional

import ipyvuetify as v
import pandas as pd
from ipywidgets import DOMWidget, link
from ipywidgets.widgets.widget import widget_serialization
from traitlets import Bool, Dict, HasTraits, Instance, Int, List, Unicode, observe

from pysepal.solara.theme import ThemeState, get_current_theme_state

logger = logging.getLogger("sepalui.vue_app")

_LOCALE_STATE_REMOVED = (
    "locale_state= was removed in pysepal 4.0: the locale is one Solara reactive per "
    "kernel. Read it with pysepal.i18n.current_locale() and write it with "
    "pysepal.i18n.set_locale()."
)


class MapApp(v.VuetifyTemplate):
    """The map application shell. Render it with ``MapApp.element(...)``.

    An application is a Solara component, and this is the shell it renders:
    ``MapApp.element(...)`` mounts the language selector and lets every nested
    element follow the locale. Constructing the widget directly gives the bare
    layout only -- no selector, and nothing that follows a language change,
    because outside a render there is no render loop. It is not a way to
    assemble an application.
    """

    template_file = Unicode(str(Path(__file__).parents[1] / "sepalwidgets/vue/MapApp.vue")).tag(
        sync=True
    )

    app_title = Unicode("Map Application").tag(sync=True)
    app_icon = Unicode("mdi-earth").tag(sync=True)
    repo_url = Unicode("").tag(sync=True)
    docs_url = Unicode("").tag(sync=True)

    dialog_width = Int(800).tag(sync=True)
    dialog_fullscreen = Bool(False).tag(sync=True)

    main_map = List(Instance(DOMWidget)).tag(sync=True, **widget_serialization)
    theme_toggle = List(Instance(DOMWidget)).tag(sync=True, **widget_serialization)
    language_selector = List(Instance(DOMWidget)).tag(sync=True, **widget_serialization)
    right_panel = List(Instance(DOMWidget)).tag(sync=True, **widget_serialization)

    right_panel_open = Bool(False).tag(sync=True)
    right_panel_width = Int(300).tag(sync=True)

    is_pinned = Bool(True).tag(sync=True)

    drawer_width = Int(320).tag(sync=True)
    "Current drawer pixel width (collapsed or expanded). Pushed from Vue."

    window_width = Int(0).tag(sync=True)
    window_height = Int(0).tag(sync=True)
    "Browser window size, pushed from Vue on mount and resize."

    right_panel_config = Dict(
        default_value={
            "title": "Extra Content",
            "icon": "mdi-widgets",
            "width": 300,
            "description": "",
            "toggle_icon": "mdi-chevron-left",
        }
    ).tag(sync=True)

    right_panel_content = List(
        Dict(
            {
                "title": Unicode(),
                "icon": Unicode(),
                "content": List(Instance(DOMWidget)),
                "divider": Bool(),
                "description": Unicode(),
            }
        ),
        default_value=[],
    ).tag(sync=True, **widget_serialization)

    steps_data = List(
        Dict(
            {
                "id": Int(),
                "name": Unicode(),
                "icon": Unicode(),
                "display": Unicode(),
                "right_panel_action": Unicode(),
                "content": List(Instance(DOMWidget)),
                "content_enabled": Bool(),
                "actions": List(),
                "width": Int(),
                "height": Int(),
            }
        )
    ).tag(sync=True, **widget_serialization)

    initial_step = Int(allow_none=True).tag(sync=True)
    current_step = Int(allow_none=True).tag(sync=True)
    step_open = Bool(False).tag(sync=True)

    @classmethod
    def element(cls, **kwargs):
        """Let Reacton render the selector before constructing the widget shell."""
        from pysepal.solara.components.locale_select import LocaleSelectComponent

        if not kwargs.get("language_selector"):
            kwargs["language_selector"] = [LocaleSelectComponent(locales=kwargs.get("locales"))]
        return super().element(**kwargs)

    def __init__(
        self,
        theme_toggle: "ThemeToggle" = None,
        theme_state: Optional[ThemeState] = None,
        locales: Optional[Iterable[str]] = None,
        initial_step: Optional[int] = None,
        model: Optional[HasTraits] = None,
        **kwargs,
    ):
        """Instantiate the MapApp class.

        Parameters
        ----------
        theme_toggle : ThemeToggle, optional
            Theme toggle widget
        theme_state : ThemeState, optional
            Shared theme state; defaults to the current scope's.
        locales : iterable of str, optional
            Locale codes the selector ``MapApp.element`` mounts will offer,
            normally ``messages.available_locales()``. Unused when a
            ``language_selector`` is supplied, and by the bare widget, which
            mounts no selector.
        initial_step : int, optional
            Initial step to display
        model : HasTraits, optional
            Model to bind with. If provided, will automatically link matching traitlets
        **kwargs
            Additional parameters
        """
        if "locale_state" in kwargs:
            raise TypeError(_LOCALE_STATE_REMOVED)

        self._theme_state = theme_state or get_current_theme_state()
        self._model = model
        self._model_links = []  # Store links for cleanup
        kwargs["theme_toggle"] = self._coerce_theme_toggle(theme_toggle, self._theme_state)

        # Create right panel from parameters if content or config is provided
        right_panel = None
        if kwargs.get("right_panel_content") or kwargs.get("right_panel_config"):
            config = kwargs.get("right_panel_config", {})
            content_data = kwargs.get("right_panel_content", [])

            right_panel = RightPanel(config=config, content_data=content_data)

            # Check if right_panel_open was specified and apply it
            if "right_panel_open" in kwargs:
                right_panel.is_open = kwargs["right_panel_open"]

        kwargs["right_panel"] = [right_panel] if right_panel else []

        # Set up right panel state tracking
        if right_panel:
            kwargs["right_panel_open"] = right_panel.is_open
            kwargs["right_panel_width"] = right_panel.config.get("width", 300)

        kwargs["language_selector"] = self._coerce_locale_select(kwargs.get("language_selector"))

        # Handle initial step configuration
        if initial_step is not None:
            kwargs["initial_step"] = initial_step
            kwargs["current_step"] = initial_step

        super().__init__(**kwargs)

        # Set up right panel state observation after initialization
        if right_panel:
            right_panel.observe(self._on_right_panel_change, "is_open")
            right_panel.observe(self._on_right_panel_config_change, "config")

        # Set up automatic model binding if model is provided
        if self._model is not None:
            self._setup_model_binding()

        # Push overlay insets to the embedded map so fit_bounds targets the visible region.
        self.observe(
            self._sync_map_insets,
            [
                "drawer_width",
                "right_panel_open",
                "right_panel_width",
                "window_width",
                "window_height",
                "main_map",
            ],
        )
        self.observe(self._sync_map_theme_state, ["theme_toggle", "main_map"])
        self.observe(self._sync_right_panel, ["right_panel_config", "right_panel_content"])
        self._sync_map_insets()
        self._sync_map_theme_state()

    def _coerce_theme_toggle(
        self, theme_toggle, theme_state: Optional[ThemeState]
    ) -> list["ThemeToggle"]:
        """Normalize theme toggle input and bind it to the given theme state."""
        if isinstance(theme_toggle, list):
            widgets = list(theme_toggle)
        elif isinstance(theme_toggle, tuple):
            widgets = list(theme_toggle)
        elif theme_toggle is None:
            widgets = []
        else:
            widgets = [theme_toggle]

        if widgets:
            widget = widgets[0]
            if hasattr(widget, "bind_theme_state"):
                widget.bind_theme_state(theme_state)
            return widgets

        return [ThemeToggle(theme_state=theme_state)]

    def _coerce_locale_select(self, language_selector) -> list[DOMWidget]:
        """Normalize explicitly supplied language-selector widgets."""
        if isinstance(language_selector, (list, tuple)):
            return list(language_selector)
        if language_selector is None:
            return []
        return [language_selector]

    # Mirror of MapApp.vue: viewports below this width dock the right
    # panel as a bottom sheet sized at NARROW_PANEL_HEIGHT_VH of the
    # window height. Both values must stay in sync with the .vue file.
    _NARROW_BREAKPOINT_PX = 960
    _NARROW_PANEL_HEIGHT_VH = 0.45

    def _sync_map_insets(self, *args):
        """Push drawer / right-panel pixel widths + window size onto the map."""
        if not self.main_map:
            return
        map_widget = self.main_map[0]
        if not hasattr(map_widget, "viewport_inset_left"):
            return
        is_narrow = 0 < self.window_width < self._NARROW_BREAKPOINT_PX
        has_right_panel = bool(self.right_panel)
        map_widget.viewport_inset_left = int(self.drawer_width)
        # In narrow mode the right panel is docked at the bottom, so it
        # consumes height (mirrored below) rather than width.
        map_widget.viewport_inset_right = (
            int(self.right_panel_width) if self.right_panel_open and not is_narrow else 0
        )
        if hasattr(map_widget, "viewport_inset_bottom"):
            bottom = (
                int(self.window_height * self._NARROW_PANEL_HEIGHT_VH)
                if is_narrow and has_right_panel
                else 0
            )
            map_widget.viewport_inset_bottom = bottom
        if self.window_width > 0 and hasattr(map_widget, "canvas_width_px"):
            map_widget.canvas_width_px = int(self.window_width)
        if self.window_height > 0 and hasattr(map_widget, "canvas_height_px"):
            map_widget.canvas_height_px = int(self.window_height)

    def _sync_map_theme_state(self, *args):
        """Push the current theme state into the embedded map."""
        if not self.main_map:
            return

        map_widget = self.main_map[0]
        if hasattr(map_widget, "bind_theme_state"):
            map_widget.bind_theme_state(self._resolve_theme_state())

    def _resolve_theme_state(self) -> ThemeState:
        """Resolve the theme state from the mounted toggle when available."""
        if self.theme_toggle and hasattr(self.theme_toggle[0], "get_theme_state"):
            theme_state = self.theme_toggle[0].get_theme_state()
            if theme_state is not None:
                return theme_state
        return self._theme_state

    def vue_set_drawer_width(self, width):
        """Receive the real drawer pixel width from Vue on mount/mini-toggle."""
        try:
            self.drawer_width = int(width)
        except (TypeError, ValueError):
            pass

    def vue_set_window_size(self, size):
        """Receive the real browser window size from Vue on mount/resize."""
        try:
            self.window_width = int(size.get("w", 0))
            self.window_height = int(size.get("h", 0))
        except (TypeError, ValueError, AttributeError):
            pass

    def _setup_model_binding(self):
        """Set up automatic two-way binding with the provided model.

        This method automatically links matching traitlets between MapApp and the model.
        """
        logger.info("Setting up model binding...")
        if self._model is None:
            return

        # Get all traitlet names from both objects
        app_traits = set(self.trait_names())
        model_traits = set(self._model.trait_names())

        common_traits = app_traits.intersection(model_traits)

        # Set up bidirectional links for common traits
        for trait_name in common_traits:
            if trait_name.startswith("_") or trait_name in [
                "template_file",
                "main_map",
                "theme_toggle",
                "language_selector",
                "right_panel",
                "steps_data",
                "right_panel_content",
            ]:
                continue

            try:
                model_link = link((self, trait_name), (self._model, trait_name))
                self._model_links.append(model_link)
            except Exception as e:
                logger.warning(f"Could not link {trait_name}: {e}")

    def unlink_model(self):
        """Remove all model links and cleanup."""
        for model_link in self._model_links:
            model_link.unlink()
        self._model_links.clear()
        self._model = None

    def set_model(self, model: HasTraits):
        """Set or change the bound model.

        Parameters
        ----------
        model : HasTraits
            New model to bind with
        """
        # Cleanup existing links
        self.unlink_model()

        # Set new model and create links
        self._model = model
        if model is not None:
            self._setup_model_binding()

    def vue_handle_right_panel_action(self, action):
        """Handle right panel actions from step activation."""
        if self.right_panel and len(self.right_panel) > 0:
            panel = self.right_panel[0]
            if action == "open":
                panel.is_open = True
            elif action == "close":
                panel.is_open = False
            elif action == "toggle":
                panel.is_open = not panel.is_open

    def vue_handle_step_change(self, step_id, is_open):
        """Handle step activation/deactivation from Vue component.

        Parameters
        ----------
        step_id : int
            The ID of the step being changed
        is_open : bool
            Whether the step is being opened or closed
        """
        self.current_step = step_id if is_open else None
        self.step_open = is_open

    def vue_handle_step_activation(self, step_id):
        """Handle step activation from Vue component.

        Parameters
        ----------
        step_id : int
            The ID of the step being activated
        """
        self.current_step = step_id
        self.step_open = True

    def vue_handle_step_deactivation(self, *args):
        """Handle step deactivation from Vue component."""
        self.current_step = None
        self.step_open = False

    def _on_right_panel_change(self, change):
        """Update the right panel state when it changes."""
        self.right_panel_open = change["new"]

    def _on_right_panel_config_change(self, change):
        """Update the right panel width when config changes."""
        new_config = change["new"]
        if "width" in new_config:
            self.right_panel_width = new_config["width"]

    def _sync_right_panel(self, *args):
        """Mirror panel config and content onto the child widget that renders them.

        ``RightPanel`` is built once in ``__init__`` from the values passed
        then, and it -- not ``MapApp`` -- is what the panel renders from. Without
        this the sibling observers only run child -> parent, so a re-render
        updated these traits and the panel kept showing the strings it was born
        with. It does not recurse: ``_on_right_panel_config_change`` writes
        ``right_panel_width``, never ``right_panel_config``.
        """
        if not self.right_panel:
            return
        panel = self.right_panel[0]
        panel.config = self.right_panel_config
        panel.content_data = self.right_panel_content


class ThemeToggle(v.VuetifyTemplate):

    template_file = Unicode(str(Path(__file__).parents[1] / "sepalwidgets/vue/Theming.vue")).tag(
        sync=True
    )

    dark = Bool(None, allow_none=True).tag(sync=True)
    resolved_dark = Bool(False).tag(sync=True)
    enable_auto = Bool(True).tag(sync=True)
    on_icon = Unicode("mdi-weather-night").tag(sync=True)
    off_icon = Unicode("mdi-white-balance-sunny").tag(sync=True)
    auto_icon = Unicode("mdi-auto-fix").tag(sync=True)

    def __init__(self, theme_state: Optional[ThemeState] = None, **kwargs):
        """Initialize the toggle, optionally bound to a shared ThemeState."""
        self._theme_state = None
        super().__init__(**kwargs)
        if theme_state is not None:
            self.bind_theme_state(theme_state)

    def bind_theme_state(self, theme_state: Optional[ThemeState]) -> None:
        """Bind the toggle widget to a shared theme state."""
        if theme_state is self._theme_state:
            return

        if self._theme_state is not None:
            self._theme_state.unobserve(self._on_theme_state_mode_change, "mode")
            self._theme_state.unobserve(self._on_theme_state_dark_change, "dark")

        self._theme_state = theme_state
        if self._theme_state is None:
            return

        self.dark = ThemeState.mode_to_widget_dark(self._theme_state.mode)
        self.resolved_dark = bool(self._theme_state.dark)
        self._theme_state.observe(self._on_theme_state_mode_change, "mode")
        self._theme_state.observe(self._on_theme_state_dark_change, "dark")

    def get_theme_state(self) -> Optional[ThemeState]:
        """Return the currently bound theme state."""
        return self._theme_state

    @observe("dark")
    def _on_dark_change(self, change):
        """Mirror widget mode changes into the shared theme state."""
        if self._theme_state is not None:
            self._theme_state.set_mode(ThemeState.widget_dark_to_mode(change["new"]))

    @observe("resolved_dark")
    def _on_resolved_dark_change(self, change):
        """Mirror frontend-resolved dark/light into the shared theme state."""
        if self._theme_state is not None:
            self._theme_state.set_dark(change["new"])

    def _on_theme_state_mode_change(self, change):
        """Mirror external theme mode changes back into the widget."""
        self.dark = ThemeState.mode_to_widget_dark(change["new"])

    def _on_theme_state_dark_change(self, change):
        """Mirror external resolved dark/light changes back into the widget."""
        self.resolved_dark = bool(change["new"])


class RightPanel(v.VuetifyTemplate):

    template_file = Unicode(str(Path(__file__).parents[1] / "sepalwidgets/vue/RightPanel.vue")).tag(
        sync=True
    )

    is_open = Bool(False).tag(sync=True)
    disabled = Bool(False).tag(sync=True)

    config = Dict(
        default_value={
            "title": "Extra Content",
            "icon": "mdi-widgets",
            "width": 300,
            "description": "",
            "toggle_icon": "mdi-chevron-left",
        }
    ).tag(sync=True)

    content_data = List(
        Dict(
            {
                "title": Unicode(),
                "icon": Unicode(),
                "content": List(Instance(DOMWidget)),
                "divider": Bool(),
                "description": Unicode(),
            }
        ),
        default_value=[],
    ).tag(sync=True, **widget_serialization)

    def __init__(self, **kwargs):
        """Initialize RightPanel with event handlers."""
        super().__init__(**kwargs)

    def vue_panel_state_changed(self, state):
        """Handle panel state changes from Vue component."""
        self.is_open = state


class LocaleSelect(v.VuetifyTemplate):
    """Vue transport rendered by ``LocaleSelectComponent``."""

    template_file = Unicode(
        str(Path(__file__).parents[1] / "sepalwidgets/vue/LocaleSelect.vue")
    ).tag(sync=True)

    COUNTRIES: pd.DataFrame = pd.read_parquet(Path(__file__).parents[1] / "data" / "locale.parquet")
    available_locales = List([{"code": "en", "name": "English", "flag": "gb"}]).tag(sync=True)
    value = Unicode("en").tag(sync=True)
