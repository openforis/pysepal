"""Solara language selector with browser-owned initial resolution."""

from typing import Iterable, Optional

import solara

from pysepal.i18n import current_locale, set_locale
from pysepal.sepalwidgets.vue_app import LocaleSelect
from pysepal.solara.locale import describe_offered_locales


@solara.component
def LocaleSelectComponent(locales: Optional[Iterable[str]] = None):
    """Select the current kernel's language and update subscribed components.

    Args:
        locales: Offered catalogue locale codes; defaults to English.
    """
    offered = solara.use_memo(
        lambda: describe_offered_locales(
            ["en"] if locales is None else locales,
            LocaleSelect.COUNTRIES.to_dict(orient="records"),
        ),
        dependencies=[locales],
    )
    return LocaleSelect.element(
        available_locales=offered,
        value=current_locale(),
        on_value=set_locale,
    )
