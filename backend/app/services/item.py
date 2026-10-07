from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.core.exceptions import NotFound
from app.models import Item
from app.repositories.item import ItemRepository
from app.schemas.item import ItemCreate, ItemUpdate


class ItemService:
    """비즈니스 로직과 트랜잭션 경계(commit)를 담당합니다."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = ItemRepository(db)

    def get(self, item_id: int) -> Item:
        item = self.repo.get(item_id)
        if item is None:
            raise NotFound(f"Item {item_id} not found")
        return item

    def list(self, offset: int, limit: int) -> Sequence[Item]:
        return self.repo.list(offset, limit)

    def create(self, data: ItemCreate) -> Item:
        item = self.repo.add(Item(**data.model_dump()))
        self.db.commit()
        self.db.refresh(item)
        return item

    def update(self, item_id: int, data: ItemUpdate) -> Item:
        item = self.get(item_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(item, field, value)
        self.db.commit()
        self.db.refresh(item)
        return item

    def delete(self, item_id: int) -> None:
        self.repo.delete(self.get(item_id))
        self.db.commit()
