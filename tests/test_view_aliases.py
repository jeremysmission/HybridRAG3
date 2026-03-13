from src.gui.panels.panel_keys import normalize_view_key


def test_tuning_alias_routes_to_admin_view():
    assert normalize_view_key("tuning") == "admin"
    assert normalize_view_key("TUNING") == "admin"


def test_ref_alias_routes_to_reference_view():
    assert normalize_view_key("ref") == "reference"


def test_command_center_aliases_route_to_commands_view():
    assert normalize_view_key("cli") == "commands"
    assert normalize_view_key("command-center") == "commands"
    assert normalize_view_key("toolbox") == "commands"
