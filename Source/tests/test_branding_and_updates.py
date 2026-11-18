import builtins

from bookworm import app
from bookworm.config.spec import config_spec
from bookworm.gui.book_viewer.menu_constants import ViewerMenuIds
from bookworm.service.handler import BUILTIN_SERVICES


def test_local_product_name_is_used_in_user_visible_text():
    assert app.display_name == "飞船阅读"
    assert app.brand_text("About Bookworm") == "About 飞船阅读"
    assert builtins._("About Bookworm") == "About 飞船阅读"


def test_application_update_component_is_not_registered_or_configurable():
    service_names = {service.name for service in BUILTIN_SERVICES}
    spec_text = config_spec.getvalue()

    assert "otau" not in service_names
    assert "auto_check_for_updates" not in spec_text
    assert "last_update_check" not in spec_text
    assert "changelog" not in ViewerMenuIds.__members__
    assert not hasattr(app, "update_url")
    assert not hasattr(app, "changelog_url")
