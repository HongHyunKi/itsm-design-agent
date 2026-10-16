# 새 모델은 여기 import 해야 Base.metadata(Alembic autogenerate)에 잡힙니다.
from app.models.base import Base

__all__ = ["Base"]
