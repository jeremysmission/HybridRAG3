#!/usr/bin/env python
"""
Populate the online-mode credentials that the GUI stores so the CLI autotune can
pick them up. Run this once after copying the endpoint/token from the GUI's LLM tab.
"""

from pathlib import Path
import os
import yaml


def load_yaml(path: Path) -> dict:
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def save_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f, sort_keys=False)


def prompt_if_missing(value: str, prompt: str) -> str:
    if value:
        return value
    return input(prompt).strip()


def main() -> None:
    overrides_path = Path("config/user_overrides.yaml")
    overrides = load_yaml(overrides_path)

    api_section = overrides.get("api", {})

    endpoint = prompt_if_missing(
        api_section.get("endpoint", ""), "Enter online API endpoint (e.g. https://your.openrouter.com/chat): "
    )
    auth_scheme = prompt_if_missing(
        api_section.get("auth_scheme", "bearer"),
        "Auth scheme (bearer/api_key, default= bearer): ",
    ) or "bearer"

    api_section["endpoint"] = endpoint
    api_section["auth_scheme"] = auth_scheme
    api_section["provider"] = prompt_if_missing(api_section.get("provider", ""), "Provider (azure/openai): ") or "openai"
    api_section["model"] = prompt_if_missing(api_section.get("model", ""), "Model name o retrieve (e.g. gpt-4o-mini): ")
    overrides["api"] = api_section

    save_yaml(overrides_path, overrides)

    print("\nUpdated config/user_overrides.yaml with your online API details.")
    print("Now set your API key in the environment before running autotune.")
    print("Windows example (run in the same terminal before the Python call):")
    print('  setx OPENAI_API_KEY "sk-xxxx"')
    print("Then restart your shell so the variable is available, or prefix the autotune run with:")
    print('  set OPENAI_API_KEY=sk-xxxx && python tools/run_mode_autotune.py --workflow full --mode online')


if __name__ == "__main__":
    main()
