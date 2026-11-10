from pathlib import Path

APP_NAME = "whaat"


def state_dir(instance_suffix: str = "") -> Path:
    return Path.home() / "Library" / "Application Support" / f"{APP_NAME}{instance_suffix}"
