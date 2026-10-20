"""Deterministic JSON, with no ambiguous numbers, duplicate keys or coercions."""
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime
from enum import Enum
import hashlib
import json
import math
from typing import Any

from .errors import SazuError, require


def _default(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, datetime):
        require(value.tzinfo is not None)
        return value.astimezone(UTC).isoformat().replace('+00:00', 'Z')
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    raise SazuError('INVALID_INPUT')


def _check_keys(value: Any) -> None:
    if is_dataclass(value) and not isinstance(value, type):
        _check_keys(asdict(value))
    elif isinstance(value, dict):
        require(all(type(key) is str for key in value))
        for item in value.values():
            _check_keys(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            _check_keys(item)


def canonical_json(value: Any) -> str:
    try:
        _check_keys(value)
        return json.dumps(value, default=_default, sort_keys=True,
                          separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, OverflowError, RecursionError):
        raise SazuError('INVALID_INPUT') from None


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()


def parse_request(text: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            require(key not in result)
            result[key] = value
        return result

    def bad_constant(_: str) -> None:
        raise SazuError('INVALID_INPUT')

    def finite_float(text: str) -> float:
        result = float(text)
        require(math.isfinite(result))
        return result

    try:
        value = json.loads(text, object_pairs_hook=pairs, parse_constant=bad_constant,
                           parse_float=finite_float)
        require(type(value) is dict)
        return value
    except (ValueError, TypeError, RecursionError):
        raise SazuError('INVALID_INPUT') from None
