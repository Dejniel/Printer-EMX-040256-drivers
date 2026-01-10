from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SocketLike = Any


@dataclass(frozen=True)
class DeviceInfo:
    name: str
    address: str
