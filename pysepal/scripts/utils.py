"""All the helper function of sepal-ui."""

import configparser
import math
import random
import re
import string
import warnings
from pathlib import Path
from typing import Any, Optional, Sequence, Tuple, Union
from urllib.parse import urlparse

import ee
import ipyvuetify as v
import requests
import tomli
from anyascii import anyascii
from deprecated.sphinx import deprecated, versionadded

import pysepal

# check_input takes a `msg` parameter, which shadows the lookup.
from pysepal.message import msg as _msg
from pysepal.scripts import decorator as sd
from pysepal.scripts.gee import init_ee  # noqa: F401 - backward compatibility
from pysepal.scripts.warning import SepalWarning

# Types
Pathlike = Union[str, Path]


def hide_component(widget: v.VuetifyWidget) -> v.VuetifyWidget:
    """Hide a vuetify based component.

    Args:
        widget: the widget to hide

    Returns:
        the widget
    """
    if isinstance(widget, pysepal.sepalwidgets.sepalwidget.SepalWidget):
        widget.hide()

    elif "d-none" not in str(widget.class_):
        widget.class_ = str(widget.class_).strip() + " d-none"

    return widget


def show_component(widget: v.VuetifyWidget) -> v.VuetifyWidget:
    """Show a vuetify based component.

    Args:
        widget: the widget to hide

    Returns:
        the widget
    """
    if isinstance(widget, pysepal.sepalwidgets.sepalwidget.SepalWidget):
        widget.show()

    elif "d-none" in str(widget.class_):
        widget.class_ = widget.class_.replace("d-none", "")

    return widget


def create_download_link(pathname: Pathlike) -> str:
    """Create a clickable link to download the pathname target.

    Args:
        pathname: the pathname th download

    Returns:
        the download link
    """
    # return the link if it's an absolute url
    if isinstance(pathname, str) and bool(urlparse(str(pathname)).netloc):
        return pathname

    # create a downloadable link from the jupyter node
    pathname = Path(pathname)
    try:
        download_path = pathname.relative_to(Path.home())
    except ValueError:
        download_path = pathname

    # I want to use the ipyurl lib to guess the url of the Jupyter server on the fly
    # but I don't really understand how it works
    # so here is an ugly fix only compatible with SEPAL
    link = f"https://sepal.io/api/sandbox/jupyter/files/{download_path}"

    return link


def random_string(string_length: int = 3) -> str:
    """Generates a random string of fixed length.

    Args:
        string_length: Fixed length. Defaults to 3.

    Returns:
        A random string
    """
    letters = string.ascii_lowercase

    return "".join(random.choice(letters) for i in range(string_length))


def get_file_size(filename: Pathlike) -> str:
    """Get the file size as string of 2 digit in the adapted scale (B, KB, MB....).

    Args:
        filename: the path to the file to measure

    Returns:
        the file size in a readable humanly readable
    """
    file_size = Path(filename).stat().st_size

    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = math.floor(math.log(file_size, 1024)) if file_size > 0 else 0
    s = file_size / (1024**i)

    return "{:.1f} {}".format(s, size_name[i])


def normalize_str(msg: str, folder: bool = True) -> str:
    """Normalize an str to make it compatible with file naming (no spaces, special chars ...etc).

    Params:
        msg: the string to sanitise
        folder: if the name will be used for folder naming or for display. if display, <'> and < > characters will be kept

    Returns:
        the modified str
    """
    regex = r"[^a-zA-Z\d\-_]" if folder else r"[^a-zA-Z\d\-_ ']"

    return re.sub(regex, "_", anyascii(msg))


def to_colors(in_color: Union[str, Sequence], out_type: str = "hex") -> Union[str, tuple]:
    """Transform any color type into a color in the specified output format.

    Available format: [hex]

    Args:
        in_color: It can be a string (e.g., 'red', '#ffff00', 'ffff00') or RGB tuple (e.g., (255, 127, 0)).
        out_type: the type of the output color from ['hex']. default to 'hex'

    Returns:
        The color in the specified format. default to black.
    """
    # imported lazily: importing matplotlib at module load time makes it create
    # ~/.config/matplotlib on first `import pysepal`, even on a read-only $HOME
    from matplotlib import colors as c

    # list of the color function used for the translation
    c_func = {"hex": c.to_hex}
    transform = c_func[out_type]

    out_color = "#000000"  # default black color

    if isinstance(in_color, tuple) and len(in_color) == 3:
        # rescale color if necessary
        if all(isinstance(item, int) for item in in_color):
            in_color = [c / 255.0 for c in in_color]

        return transform(in_color)

    else:
        # try to guess the color system
        try:
            return transform(in_color)
        except Exception:
            pass

        # try again by adding an extra # (GEE handle hex codes without #)
        try:
            return transform(f"#{in_color}")
        except Exception:
            pass

    return transform(out_color)


def next_string(string: str) -> str:
    """Create a string followed by an underscore and a consecutive number.

    Args:
        string: the initial string

    Returns:
        the incremented string
    """
    # if the string is already numbered the last digit is separated from the rest of the string by an "_"
    split = string.split("_")
    end = split[-1]

    if end.isdigit():
        string = "_".join(split[:-1]) + f"_{int(end)+1}"
    else:
        string += "_1"

    return string


@versionadded(version="2.7.1")
def set_type(color: str) -> str:
    r"""Return a pre-defined material colors based on the requested type\_ parameter.

    If the parameter is not a predefined color, fallback to "info" and will raise a warning. the colors can only be selected from ["primary", "secondary", "accent", "error", "info", "success", "warning", "anchor"].

    Args:
        color: the requested color

    Returns:
        a pre-defined material color

    """
    from pysepal.frontend.styles import TYPES

    if color not in TYPES:
        warnings.warn(
            f'the selected color "{color}" is not a pre-defined material color. It should be one from [{", ".join(TYPES)}]',
            SepalWarning,
        )
        color = TYPES[0]

    return color


@versionadded(version="2.8.0")
def geojson_to_ee(
    geo_json: dict, geodesic: bool = False, encoding: str = "utf-8"
) -> ee.FeatureCollection:
    """Transform a geojson object into a featureCollection or a Geometry.

    No sanity check is performed on the initial geo_json. It must respect the
    `__geo_interface__ <https://gist.github.com/sgillies/2217756>`__.

    Args:
        geo_json: a geo_json dictionary
        geodesic: Whether line segments should be interpreted as spherical geodesics. If false, indicates that line segments should be interpreted as planar lines in the specified CRS. If absent, defaults to True if the CRS is geographic (including the default EPSG:4326), or to False if the CRS is projected. Defaults to False.
        encoding: The encoding of characters. Defaults to "utf-8".

    Returns:
        the created featurecollection
    """
    # from a featureCollection
    if geo_json["type"] == "FeatureCollection":
        for feature in geo_json["features"]:
            if feature["geometry"]["type"] != "Point":
                feature["geometry"]["geodesic"] = geodesic
        features = ee.FeatureCollection(geo_json)
        return features

    # from a single feature
    elif geo_json["type"] == "Feature":
        geom = None
        # Checks whether it is a point
        if geo_json["geometry"]["type"] == "Point":
            coordinates = geo_json["geometry"]["coordinates"]
            longitude = coordinates[0]
            latitude = coordinates[1]
            geom = ee.Geometry.Point(longitude, latitude)
        # for every other geometry simply create a geometry
        else:
            geom = ee.Geometry(geo_json["geometry"], "", geodesic)

        return geom

    # some error handling because we are fancy
    else:
        raise ValueError("Could not convert the geojson to ee.Geometry()")

    return


def check_input(input_: Any, msg: Optional[str] = None) -> bool:
    r"""Check if the inpupt value is initialized.

    If not raise an error, else return True.

    Args:
        input\_: the input to check
        msg: the message to display if the input is not set

    Return:
        check if the value is initialized
    """
    msg = _msg("utils.check_input.error") if msg is None else msg

    # by the default the variable is considered valid
    init = True

    # check the collection type that are the only one supporting the len method
    try:
        init = False if len(input_) == 0 else init
    except Exception:
        init = False if input_ is None else init

    if init is False:
        raise ValueError(msg)

    return init


def get_app_version(repo_folder: Pathlike = Path.cwd()) -> str:
    """Get the current version of the a github project using the pyproject.toml file in the root.

    Returns:
        the version of the repository
    """
    # get the path to the pyproject.toml file
    pyproject_path = repo_folder / "pyproject.toml"

    # check if the file exist
    if pyproject_path.exists():
        # read the file using tomli
        pyproject = tomli.loads(pyproject_path.read_text())

        # get the version
        return pyproject.get("project", {}).get("version", None)

    return None


def get_repo_info(repo_folder: Pathlike = Path.cwd()) -> Tuple[str, str]:
    """Get the repository name and owner from the git config file."""
    config = configparser.ConfigParser()
    git_config_path = Path(repo_folder) / ".git/config"

    # Handle case when git config has duplicate options
    try:
        config.read(git_config_path)
    except configparser.DuplicateOptionError:
        if not git_config_path.exists():
            return "", ""

        remote_url = ""
        in_origin_section = False

        with open(git_config_path, "r") as f:
            for line in f:
                line = line.strip()
                if line == '[remote "origin"]':
                    in_origin_section = True
                elif line.startswith("[") and in_origin_section:
                    in_origin_section = False
                elif in_origin_section and line.startswith("url = "):
                    remote_url = line.split("url = ")[1]
                    break

        if not remote_url:
            return "", ""
    else:
        try:
            remote_url = config.get('remote "origin"', "url")
        except (configparser.NoSectionError, configparser.NoOptionError):
            return "", ""

    # Check if URL is likely SSH
    if "git@" in remote_url:
        match = re.search(r":(.*?)/(.*?)(?:\.git)?$", remote_url)

    # Assume URL is HTTPS otherwise
    else:
        match = re.search(r"github\.com/(.*?)/(.*?)(?:\.git)?$", remote_url)

    if match:
        return match.groups()

    else:
        return "", ""


def get_changelog(repo_folder: Pathlike = Path.cwd()) -> str:
    """Check if the repository contains a changelog file and/or a remote release and return its content.

    Returns:
        str: the content of the release and/or changelog file
    """
    changelog_text, release_text = "", ""
    repo_owner, repo_name = get_repo_info(repo_folder)

    release_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases/latest"

    response = requests.get(release_url)
    if all([repo_owner, repo_name]) and response.status_code == 200:
        response_json = response.json()
        name = response_json.get("name")

        if name == f"v_{get_app_version()}":
            release_text = response_json.get("body")

            url_pattern = r"https://github\.com/[^ ]+/pull/\d+"

            # Replace URLs with <a> tags
            def wrap_url_in_a_tag(match):
                url = match.group(0)
                return f'<a href="{url}">{url}</a>'

            release_text = re.sub(url_pattern, wrap_url_in_a_tag, release_text)

    # get the path to the pyproject.toml file
    changelog_path = Path(repo_folder) / "CHANGELOG.md"

    # check if the file exist
    if changelog_path.exists():
        changelog_text = changelog_path.read_text()

    return release_text, changelog_text


################################################################################
# the soon to be deprecated decorators
#

# fmt: off
catch_errors = deprecated(version='3.0', reason="use pysepal.scripts.decorator.catch_errors instead")(sd.catch_errors)
need_ee = deprecated(version='3.0', reason="use pysepal.scripts.decorator.need_ee instead")(sd.need_ee)
loading_button = deprecated(version='3.0', reason="use pysepal.scripts.decorator.need_ee instead")(sd.loading_button)
switch = deprecated(version='3.0', reason="use pysepal.scripts.decorator.switch instead")(sd.switch)
# fmt: on
