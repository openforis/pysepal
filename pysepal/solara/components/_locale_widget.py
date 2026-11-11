"""Vue transport of the language selector, rendered by ``LocaleSelectComponent``."""

from pathlib import Path

import ipyvuetify as v
import pandas as pd
from traitlets import List, Unicode

from pysepal._vuetify import compose_vue, vuetify_markup

VUE_DIR = Path(__file__).parent / "vue"


class LocaleSelectWidget(v.VuetifyTemplate):
    """Language button and dialog; the browser resolves the first locale itself."""

    template = Unicode(
        compose_vue(vuetify_markup(VUE_DIR / "LocaleSelect"), VUE_DIR / "LocaleSelect.js")
    ).tag(sync=True)

    COUNTRIES: pd.DataFrame = pd.read_parquet(Path(__file__).parents[2] / "data" / "locale.parquet")
    available_locales = List([{"code": "en", "name": "English", "flag": "gb"}]).tag(sync=True)
    value = Unicode("en").tag(sync=True)
