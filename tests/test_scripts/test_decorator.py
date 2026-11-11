"""Test the custom decorators."""

import json
import os
import warnings
from pathlib import Path

import ee
import ipyvuetify as v
import pytest

from pysepal._vuetify import IPYVUETIFY_V3
from pysepal.scripts import decorator as sd
from pysepal.scripts.warning import SepalWarning

# these tests drive the deprecated sepalwidgets, which need ipyvuetify 1
legacy = pytest.mark.skipif(IPYVUETIFY_V3, reason="sepalwidgets needs ipyvuetify 1")


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_init_ee() -> None:
    """Test the init_ee_from_token function."""
    credentials_filepath = Path(ee.oauth.get_credentials_path())
    existing = False

    try:
        # Reset credentials to force the initialization
        # It can be initiated from different imports
        ee.data.reset()

        # Get the credentials path

        # Remove the credentials file if it exists
        if credentials_filepath.exists():
            existing = True
            credentials_filepath.rename(credentials_filepath.with_suffix(".json.bak"))

        # Act: Earthengine token should be created
        sd.init_ee()

        assert credentials_filepath.exists()

        # read the back up and remove the "project_id" key
        credentials = json.loads(credentials_filepath.with_suffix(".json.bak").read_text())

        ## 2. Assert when there's no a project associated
        # remove the project_id key if it exists
        ee.data.reset()
        credentials.pop("project_id", None)
        credentials.pop("project", None)
        if "EARTHENGINE_PROJECT" in os.environ:
            del os.environ["EARTHENGINE_PROJECT"]

        # write the new credentials
        credentials_filepath.write_text(json.dumps(credentials))

        with pytest.raises(NameError) as e:
            sd.init_ee()

        # Access the exception message via `e.value`
        error_message = str(e.value)
        assert "The project name cannot be detected" in error_message

    finally:
        # restore the file
        if existing:
            credentials_filepath.with_suffix(".json.bak").rename(credentials_filepath)

        # check that no error is raised
        sd.init_ee()

    return


def test_need_ee_raises_when_not_initialized(monkeypatch) -> None:
    """@need_ee must fail loudly when EE is not initialized.

    init_ee() is best-effort (no-ops without credentials), so need_ee enforces the
    requirement: the wrapped function must not run against an uninitialized session.
    """
    monkeypatch.setattr("pysepal.scripts.gee.init_ee", lambda: None)
    monkeypatch.setattr(ee.data, "is_initialized", lambda: False)

    @sd.need_ee
    def use_ee() -> str:
        return "ran"

    with pytest.raises(Exception, match="needs an Earth Engine authentication"):
        use_ee()


@legacy
def test_catch_errors() -> None:
    """Check the catch error decorator."""
    from pysepal import sepalwidgets as sw

    # create an external alert to test the wiring
    alert = sw.Alert()

    # create a fake object that uses the decorator
    class Obj:
        def __init__(self):
            self.alert = sw.Alert()
            self.btn = sw.Btn()

        @sd.catch_errors()
        def func0(self, *args):
            return 1 / 0

        @sd.catch_errors(alert=alert)
        def func1(self, *args):
            return 1 / 0

        @sd.catch_errors()
        def func2(self, *args):
            return "toto"

        @sd.loading_button()
        def func3(self, *args):
            warnings.warn("toto")
            warnings.warn("sepal", SepalWarning)
            return 1

        @sd.loading_button()
        def func4(self, *args):
            warnings.warn("toto")
            warnings.warn("sepal", SepalWarning)
            return 1

    obj = Obj()
    with pytest.raises(Exception):
        obj.func0()

    # should return an alert error in the the self alert widget
    assert obj.alert.type == "error"

    # Reset the alert to remove previous state
    assert obj.alert.reset()

    with pytest.raises(Exception):
        obj.func1()

    # should return an alert in the external alert widget
    assert alert.type == "error"

    # check when there's no error
    assert obj.alert.reset()
    value = obj.func2()
    assert value == "toto"
    assert obj.alert.type != "error"

    # should raise warnings
    obj.alert.reset()
    with warnings.catch_warnings(record=True) as w_list:
        obj.func4(obj.btn, None, None)
        assert obj.btn.disabled is False
        assert obj.alert.type == "warning"
        assert "sepal" in obj.alert.children[1].children[0]
        assert "toto" not in obj.alert.children[1].children[0]
        msg_list = [w.message.args[0] for w in w_list]
        assert any("sepal" in s for s in msg_list)
        assert any("toto" in s for s in msg_list)


@legacy
def test_loading_button() -> None:
    """Check the loading decorator."""
    from pysepal import sepalwidgets as sw

    # create a fake object that uses the decorator
    class Obj:
        def __init__(self):
            self.alert = sw.Alert()
            self.btn = sw.Btn()

        @sd.loading_button()
        def func1(self, *args):
            return 1 / 0

        @sd.loading_button()
        def func2(self, *args):
            return 1 / 0

        @sd.loading_button()
        def func3(self, *args):
            return "toto"

    obj = Obj()

    # should only display error in the alert
    with pytest.raises(Exception):
        obj.func1(obj.btn, None, None)

    assert obj.btn.disabled is False
    assert obj.alert.type == "error"
    assert obj.btn.loading is False

    # func 3 shouldn't raise any error
    assert obj.alert.reset()
    value = obj.func3(obj.btn, None, None)

    assert value == "toto"
    assert obj.alert.type != "error"
    assert obj.btn.loading is False

    return


def test_switch() -> None:
    """Test the switch decorator."""
    # create a fake object that uses the decorator
    class Obj:
        def __init__(self):
            self.valid = True
            self.select = v.Select(disabled=False)
            self.select2 = v.Select(disabled=False)

            # apply on non string
            self.func4 = sd.switch("disabled", on_widgets=[self.select])(self.func4)

        # apply the widget on the object itself
        @sd.switch("valid")
        def func1(self, *args):
            return True

        # apply the widget on members of the object
        @sd.switch("disabled", on_widgets=["select", "select2"])
        def func2(self, *args):
            return True

        # apply it on a non existent widget
        @sd.switch("niet", on_widgets=["fake_widget"])
        def func3(self, *args):
            return True

        def func4(self, *args):
            return True

        # apply on a error func with debug = True
        @sd.switch("valid")
        def func5(self, *args):
            return 1 / 0

        # apply the switch with a non matching number of targets
        @sd.switch("disabled", on_widgets=["select", "select2"], targets=[True])
        def func6(self, *args):
            return True

    obj = Obj()

    # assert
    obj.func1()
    assert obj.valid is True

    obj.func2()
    assert obj.select.disabled is False
    assert obj.select2.disabled is False

    with pytest.raises(Exception):
        obj.func3()

    with pytest.raises(Exception):
        obj.func4()

    with pytest.raises(Exception):
        obj.func5()

    with pytest.raises(IndexError):
        obj.func6()

    return
