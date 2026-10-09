"""Solara FileInputComponent — canonical location.

Wraps the ipyvuetify FileInput widget in a Solara-native component.
"""

from typing import Callable, List, Optional, Union

import solara
from pysepal_api import SepalClient

from pysepal.scripts.filesystem import FileSystem, SandboxFileSystem
from pysepal.sepalwidgets.file_input import FileInput, _default_filesystem


@solara.component
def FileInputComponent(
    initial_folder: str = "",
    root: str = "",
    sepal_client: Optional[SepalClient] = None,
    extensions: List[str] = [],
    label: str = "Select a file",
    clearable: bool = True,
    value: Union[str, solara.Reactive[str]] = "",
    on_value: Optional[Callable[[str], None]] = None,
    filesystem: Optional[FileSystem] = None,
):
    """Solara component wrapper for FileInput widget.

    Args:
        initial_folder: The initial folder to read files from.
        root: Maximum root directory that can be accessed.
        sepal_client: Browse this client's SEPAL workspace.
        extensions: List of file extensions to filter by.
        label: Label for the file selection button.
        clearable: Whether to show a clear button.
        value: Current selected file path (can be reactive).
        on_value: Callback function when value changes.
        filesystem: Browse this filesystem. Takes precedence over ``sepal_client``.
            By default the user's files for this runtime.

    Returns:
        FileInput element configured as a Solara component.
    """
    reactive_value = solara.use_reactive(value, on_value)
    del value, on_value

    is_syncing = solara.use_ref(False)

    def make_filesystem() -> Optional[FileSystem]:
        if filesystem is not None:
            return filesystem
        if sepal_client is not None:
            return SandboxFileSystem(sepal_client)
        return _default_filesystem(root)

    fs = solara.use_memo(make_filesystem, [filesystem, sepal_client, root])

    # Resolved here, not in the widget: a re-render writes every prop back onto
    # the widget, and an unresolved "" would reset its bound.
    resolved_root = str(fs.resolve(root or fs.root)) if fs else ""
    resolved_initial = str(fs.resolve(initial_folder or resolved_root)) if fs else ""

    file_input = FileInput.element(
        initial_folder=resolved_initial,
        root=resolved_root,
        filesystem=fs,
        extensions=extensions,
        label=label,
        clearable=clearable,
        value=reactive_value.value,
        on_v_model=lambda v: None,
    )

    def setup_widget():
        real_widget = solara.get_widget(file_input)
        if real_widget is None:
            return

        if reactive_value.value and real_widget.v_model != reactive_value.value:
            real_widget.v_model = reactive_value.value

        def on_widget_change(change):
            if not is_syncing.current:
                is_syncing.current = True
                reactive_value.set(change["new"])
                is_syncing.current = False

        real_widget.observe(on_widget_change, "v_model")

        return lambda: real_widget.unobserve(on_widget_change, "v_model")

    solara.use_effect(setup_widget, [])

    def sync_to_widget():
        if is_syncing.current:
            return

        real_widget = solara.get_widget(file_input)
        if real_widget is None:
            return

        if real_widget.v_model != reactive_value.value:
            is_syncing.current = True
            real_widget.v_model = reactive_value.value
            is_syncing.current = False

    solara.use_effect(sync_to_widget, [reactive_value.value])

    return file_input
