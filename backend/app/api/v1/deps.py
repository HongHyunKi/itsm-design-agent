import logging
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.logging import get_request_logger
from app.db.session import get_db
from app.services.item import ItemService


def get_logger(request: Request) -> logging.LoggerAdapter:
    return get_request_logger(getattr(request.state, "request_id", "-"))


SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[Session, Depends(get_db)]
LoggerDep = Annotated[logging.LoggerAdapter, Depends(get_logger)]


def get_item_service(db: DbDep) -> ItemService:
    return ItemService(db)


ItemServiceDep = Annotated[ItemService, Depends(get_item_service)]
