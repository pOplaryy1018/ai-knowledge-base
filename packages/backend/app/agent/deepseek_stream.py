"""Assemble untrusted streamed tool-call deltas without executing them."""

import json
import math
from dataclasses import dataclass, field
from typing import Any, NoReturn


def _finite_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("invalid number")
    return result


def _reject_constant(_value: str) -> NoReturn:
    raise ValueError("invalid constant")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


@dataclass(frozen=True)
class AssembledToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class _CallParts:
    call_id: str | None = None
    name_parts: list[str] = field(default_factory=list)
    arguments_parts: list[str] = field(default_factory=list)
    name_bytes: int = 0
    argument_bytes: int = 0


class ToolCallAccumulator:
    """Buffer bounded deltas; return calls only after the whole batch validates."""

    def __init__(self, *, max_argument_bytes: int = 65536, max_calls: int = 32) -> None:
        if max_argument_bytes <= 0 or max_calls <= 0:
            raise ValueError("invalid stream limits")
        self._max_argument_bytes = max_argument_bytes
        self._max_calls = max_calls
        self._calls: dict[int, _CallParts] = {}
        self._failed = False
        self._finished = False

    def _reject(self) -> NoReturn:
        self._failed = True
        raise ValueError("invalid tool call stream") from None

    def feed(self, deltas: list[Any]) -> None:
        if self._failed or self._finished or not isinstance(deltas, list):
            self._reject()
        for delta in deltas:
            if not isinstance(delta, dict):
                self._reject()
            if delta.get("type") not in (None, "function"):
                self._reject()
            index = delta.get("index")
            if not isinstance(index, int) or isinstance(index, bool) or index < 0 or index >= self._max_calls:
                self._reject()
            if index not in self._calls:
                self._calls[index] = _CallParts()
            parts = self._calls[index]
            call_id = delta.get("id")
            if call_id is not None:
                if not isinstance(call_id, str) or not call_id or len(call_id) > 256:
                    self._reject()
                try:
                    if len(call_id.encode("utf-8")) > 256:
                        self._reject()
                except UnicodeEncodeError:
                    self._reject()
                if parts.call_id is not None and parts.call_id != call_id:
                    self._reject()
                parts.call_id = call_id
            function = delta.get("function")
            if function is None:
                continue
            if not isinstance(function, dict):
                self._reject()
            for key in ("name", "arguments"):
                value = function.get(key)
                if value is None:
                    continue
                if not isinstance(value, str):
                    self._reject()
                if not value:
                    continue
                try:
                    size = len(value.encode("utf-8"))
                except UnicodeEncodeError:
                    self._reject()
                if key == "name":
                    parts.name_bytes += size
                    if parts.name_bytes > 256:
                        self._reject()
                    parts.name_parts.append(value)
                else:
                    parts.argument_bytes += size
                    if parts.argument_bytes > self._max_argument_bytes:
                        self._reject()
                    parts.arguments_parts.append(value)

    def finish(self) -> list[AssembledToolCall]:
        if self._failed or self._finished:
            self._reject()
        self._finished = True
        result: list[AssembledToolCall] = []
        ids: set[str] = set()
        for index in sorted(self._calls):
            parts = self._calls[index]
            name = "".join(parts.name_parts)
            if not parts.call_id or not name or parts.call_id in ids:
                self._reject()
            try:
                arguments = json.loads(
                    "".join(parts.arguments_parts),
                    parse_constant=_reject_constant,
                    parse_float=_finite_float,
                    object_pairs_hook=_unique_object,
                )
                json.dumps(arguments, ensure_ascii=False).encode("utf-8")
            except (ValueError, RecursionError, UnicodeEncodeError):
                self._reject()
            if not isinstance(arguments, dict):
                self._reject()
            ids.add(parts.call_id)
            result.append(AssembledToolCall(parts.call_id, name, arguments))
        return result
