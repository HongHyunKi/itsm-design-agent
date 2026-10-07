"""mock/live 어댑터 분기는 이 파일에서만 합니다. 서비스는 get_*()만 호출하고 타입은 ports의 Protocol로 받습니다."""

from functools import lru_cache

from app.core.config import get_settings
from app.integrations.mock_notifier import MockNotifier
from app.integrations.ports import Notifier


def get_notifier() -> Notifier:
    if get_settings().is_live:
        return _live_notifier()
    return MockNotifier()


@lru_cache
def _live_notifier() -> Notifier:
    # live 어댑터는 함수 안에서 import 합니다(mock 모드에서 SDK 의존성 불필요). 예:
    # from app.integrations.slack_notifier import SlackNotifier
    # return SlackNotifier(token=get_settings().slack_token.get_secret_value())
    raise NotImplementedError("live Notifier 어댑터가 아직 없습니다")
