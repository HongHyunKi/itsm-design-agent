from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Item


def seed() -> None:
    with SessionLocal() as db:
        if db.scalar(select(Item.id).limit(1)) is None:
            db.add(Item(name="Sample item", description="seeded on startup"))
            db.commit()
