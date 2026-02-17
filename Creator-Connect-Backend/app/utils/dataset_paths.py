from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Union
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_PROJECT_ROOT / ".env")

def _resolve_path(value: Union[str, Path], *, allow_relative: bool = True) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute() and allow_relative:
        path = (_PROJECT_ROOT / path).resolve()
    return path.resolve()


def get_dynamic_dataset_path() -> Optional[Path]:
    """Return resolved path for INFLUENCER_DATA_PATH if configured."""
    value = os.getenv("INFLUENCER_DATA_PATH")
    if not value:
        return None
    return _resolve_path(value)

