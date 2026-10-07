import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_live_mode_requires_real_secret_key():
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(_env_file=None, app_mode="live", secret_key="change-me")
    assert Settings(_env_file=None, app_mode="live", secret_key="real-secret").is_live
    assert not Settings(_env_file=None, app_mode="mock").is_live
