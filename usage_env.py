from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}


def load_dotenv(paths: Iterable[Path] | None = None) -> None:
    candidate_paths = list(paths) if paths is not None else [
        Path.cwd() / ".env",
        Path(__file__).resolve().parent / ".env",
    ]
    seen: set[Path] = set()
    for path in candidate_paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        _load_dotenv_file(resolved)


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES:
        return False
    return default


def env_choice(name: str, choices: set[str], default: str) -> str:
    value = os.environ.get(name, "").strip().lower()
    return value if value in choices else default


def env_first(names: Iterable[str]) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value is not None and value.strip():
            return value.strip()
    return None


def env_int(
    name: str,
    default: int,
    *,
    min_value: int | None = None,
    max_value: int | None = None,
) -> int:
    value = os.environ.get(name)
    parsed = _parse_int(value)
    if parsed is None:
        return default
    if min_value is not None and parsed < min_value:
        return default
    if max_value is not None and parsed > max_value:
        return default
    return parsed


def env_int_first(
    names: Iterable[str],
    default: int | None = None,
    *,
    min_value: int | None = None,
    max_value: int | None = None,
) -> int | None:
    parsed = _parse_int(env_first(names))
    if parsed is None:
        return default
    if min_value is not None and parsed < min_value:
        return default
    if max_value is not None and parsed > max_value:
        return default
    return parsed


def env_str(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


def _load_dotenv_file(path: Path) -> None:
    if not path.is_file():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        key_value = _parse_dotenv_line(line)
        if key_value is None:
            continue
        key, value = key_value
        os.environ.setdefault(key, value)


def _parse_dotenv_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("export "):
        stripped = stripped[7:].lstrip()
    if "=" not in stripped:
        return None
    key, raw_value = stripped.split("=", 1)
    key = key.strip()
    if not key or not key.replace("_", "").isalnum() or key[0].isdigit():
        return None
    return key, _strip_quotes(raw_value.strip())


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None
