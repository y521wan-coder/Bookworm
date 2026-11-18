# coding: utf-8

import builtins
import gettext

from bookworm import app


def install_translation(translation):
    """Install gettext functions while applying the local product name."""
    builtins._ = lambda message: app.brand_text(translation.gettext(message))
    builtins.ngettext = lambda singular, plural, number: app.brand_text(
        translation.ngettext(singular, plural, number)
    )


# Make translation functions available even before locale initialization.
install_translation(gettext.NullTranslations())
