from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Item


class ItemRepository:
    """조회와 저장만 합니다. 존재 여부 판단, commit은 서비스 몫입니다."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, item_id: int) -> Item | None:
        return self.db.get(Item, item_id)

    def list(self, offset: int, limit: int) -> Sequence[Item]:
        return self.db.scalars(select(Item).order_by(Item.id).offset(offset).limit(limit)).all()

    def add(self, item: Item) -> Item:
        self.db.add(item)
        self.db.flush()
        return item

    def delete(self, item: Item) -> None:
        self.db.delete(item)
