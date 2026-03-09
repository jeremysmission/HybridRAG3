import os

import yaml

from src.core.config import load_config, save_config_field
from src.core.user_modes import load_user_modes_data


def _write_yaml(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False)


def test_load_config_ignores_legacy_mode_tuning_when_primary_exists(tmp_path):
    cfg_dir = tmp_path / "config"
    _write_yaml(
        cfg_dir / "config.yaml",
        {
            "mode": "offline",
            "modes": {
                "offline": {
                    "retrieval": {"top_k": 4, "min_score": 0.1},
                    "ollama": {"model": "phi4-mini"},
                    "query": {"grounding_bias": 8, "allow_open_knowledge": True},
                },
                "online": {
                    "retrieval": {"top_k": 6, "min_score": 0.08},
                    "api": {"model": "gpt-4o", "deployment": "gpt-4o"},
                    "query": {"grounding_bias": 7, "allow_open_knowledge": True},
                },
            },
        },
    )
    _write_yaml(
        cfg_dir / "mode_tuning.yaml",
        {
            "modes": {
                "offline": {
                    "values": {"top_k": 99, "min_score": 0.77},
                }
            }
        },
    )

    config = load_config(str(tmp_path))

    assert config.retrieval.top_k == 4
    assert abs(config.retrieval.min_score - 0.10) < 1e-9


def test_load_config_without_primary_does_not_fallback_to_legacy_authorities(tmp_path):
    cfg_dir = tmp_path / "config"
    _write_yaml(
        cfg_dir / "default_config.yaml",
        {
            "mode": "offline",
            "retrieval": {"top_k": 17, "min_score": 0.23},
        },
    )
    _write_yaml(
        cfg_dir / "user_overrides.yaml",
        {
            "retrieval": {"top_k": 29, "min_score": 0.41},
        },
    )

    config = load_config(str(tmp_path))

    assert config.retrieval.top_k == 4
    assert abs(config.retrieval.min_score - 0.10) < 1e-9


def test_save_config_field_routes_runtime_sections_into_canonical_mode_paths(tmp_path):
    cfg_dir = tmp_path / "config"
    _write_yaml(
        cfg_dir / "config.yaml",
        {
            "mode": "offline",
            "modes": {
                "offline": {
                    "retrieval": {"top_k": 4, "min_score": 0.1},
                    "ollama": {"model": "phi4-mini"},
                    "query": {"grounding_bias": 8, "allow_open_knowledge": True},
                },
                "online": {
                    "retrieval": {"top_k": 6, "min_score": 0.08},
                    "api": {
                        "model": "gpt-4o",
                        "deployment": "gpt-4o",
                        "endpoint": "https://example.invalid",
                    },
                    "query": {"grounding_bias": 7, "allow_open_knowledge": True},
                },
            },
        },
    )

    original_root = os.environ.get("HYBRIDRAG_PROJECT_ROOT")
    os.environ["HYBRIDRAG_PROJECT_ROOT"] = str(tmp_path)
    try:
        save_config_field("retrieval.top_k", 88)
        save_config_field("api.endpoint", "https://azure-gov.example")
        save_config_field("ollama.model", "phi4:14b-q4_K_M")
    finally:
        if original_root is None:
            os.environ.pop("HYBRIDRAG_PROJECT_ROOT", None)
        else:
            os.environ["HYBRIDRAG_PROJECT_ROOT"] = original_root

    saved = yaml.safe_load((cfg_dir / "config.yaml").read_text(encoding="utf-8"))
    assert "retrieval" not in saved
    assert "api" not in saved
    assert "ollama" not in saved
    assert saved["modes"]["offline"]["retrieval"]["top_k"] == 88
    assert saved["modes"]["online"]["api"]["endpoint"] == "https://azure-gov.example"
    assert saved["modes"]["offline"]["ollama"]["model"] == "phi4:14b-q4_K_M"


def test_profile_unchecked_values_remain_agnostic(tmp_path):
    cfg_dir = tmp_path / "config"
    _write_yaml(
        cfg_dir / "config.yaml",
        {
            "mode": "offline",
            "modes": {
                "offline": {
                    "retrieval": {"top_k": 4, "min_score": 0.1},
                    "ollama": {"model": "phi4-mini"},
                    "query": {"grounding_bias": 8, "allow_open_knowledge": True},
                },
                "online": {
                    "retrieval": {"top_k": 6, "min_score": 0.08},
                    "api": {"model": "gpt-4o", "deployment": "gpt-4o"},
                    "query": {"grounding_bias": 7, "allow_open_knowledge": True},
                },
            },
        },
    )
    _write_yaml(
        cfg_dir / "user_modes.yaml",
        {
            "active_profile": "demo",
            "profiles": {
                "demo": {
                    "label": "Demo",
                    "notes": "Selective ownership",
                    "values": {
                        "modes": {
                            "offline": {
                                "retrieval": {"top_k": 99},
                            },
                            "online": {
                                "api": {"model": "gpt-4.1"},
                            },
                        }
                    },
                    "checked": {
                        "modes": {
                            "offline": {
                                "retrieval": {"top_k": False},
                            },
                            "online": {
                                "api": {"model": True},
                            },
                        }
                    },
                }
            },
        },
    )

    config = load_config(str(tmp_path))

    assert config.retrieval.top_k == 4
    assert config.api.model == "gpt-4.1"
    data = load_user_modes_data(str(tmp_path))
    assert data["profiles"]["demo"]["overrides"] == {
        "modes": {"online": {"api": {"model": "gpt-4.1"}}}
    }


def test_default_user_modes_seed_both_offline_and_online_sections(tmp_path):
    data = load_user_modes_data(str(tmp_path))
    desktop = data["profiles"]["desktop_power"]

    assert "offline" in desktop["values"]["modes"]
    assert "online" in desktop["values"]["modes"]
    assert desktop["checked"]["modes"]["offline"]["ollama"]["model"] is True
    assert desktop["checked"]["modes"]["online"]["api"]["model"] is True
