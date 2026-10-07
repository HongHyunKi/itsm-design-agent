from app.integrations.ports import NotificationResult


class MockNotifier:
    def send(self, to: str, message: str) -> NotificationResult:
        return NotificationResult(ok=True, message_id="mock")
