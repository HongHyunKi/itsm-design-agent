"""외부 연동 포트. Protocol과 결과 dataclass만 둡니다(구현 금지)."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class NotificationResult:
    ok: bool
    message_id: str | None = None


@runtime_checkable
class Notifier(Protocol):
    def send(self, to: str, message: str) -> NotificationResult: ...
