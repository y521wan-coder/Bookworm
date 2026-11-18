from bookworm.bookshelf import BookshelfService
from bookworm.gui.book_viewer.menu_constants import KEYBOARD_SHORTCUTS, ViewerMenuIds
from bookworm.gui.settings import HIDDEN_FEATURES_ICON, HiddenFeaturesPanel
from bookworm.resources import app_icons
from bookworm.webservices import WebservicesBaseService
from bookworm.webservices.url_open import UrlOpenService
from bookworm.webservices.wikiworm import WikipediaService


def test_help_commands_are_not_exposed_by_the_normal_keyboard_shortcuts():
    assert ViewerMenuIds.documentation not in KEYBOARD_SHORTCUTS


def test_web_service_commands_are_hidden_from_normal_ui():
    assert WebservicesBaseService.process_menubar(object(), None) is None
    assert UrlOpenService.process_menubar(object(), None) is None
    assert UrlOpenService.get_keyboard_shortcuts(object()) == {}
    assert WikipediaService.process_menubar(object(), None) is None
    assert WikipediaService.get_contextmenu_items(object()) == ()
    assert WikipediaService.get_keyboard_shortcuts(object()) == {}


def test_bookshelf_is_hidden_from_normal_ui_but_keeps_its_configuration():
    assert BookshelfService.process_menubar(object(), None) is None
    assert BookshelfService.get_settings_panels(object()) == ()
    assert BookshelfService.stateful_menu_ids == ()
    assert HiddenFeaturesPanel.config_section == "bookshelf"


def test_hidden_features_uses_an_existing_settings_icon():
    assert getattr(app_icons, HIDDEN_FEATURES_ICON) is not None
