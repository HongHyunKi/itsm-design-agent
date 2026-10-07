from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.v1.deps import ItemServiceDep, LoggerDep
from app.schemas.item import ItemCreate, ItemRead, ItemUpdate

router = APIRouter(prefix="/items", tags=["items"])


@router.get("", response_model=list[ItemRead], summary="[샘플 코드] 목록 조회")
def list_items(
    service: ItemServiceDep,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    return service.list(offset, limit)


@router.post("", response_model=ItemRead, status_code=status.HTTP_201_CREATED, summary="[샘플 코드] 항목 생성")
def create_item(data: ItemCreate, service: ItemServiceDep, logger: LoggerDep):
    item = service.create(data)
    logger.info("item created id=%s", item.id)
    return item


@router.get("/{item_id}", response_model=ItemRead, summary="[샘플 코드] 항목 조회")
def get_item(item_id: int, service: ItemServiceDep):
    return service.get(item_id)


@router.patch("/{item_id}", response_model=ItemRead, summary="[샘플 코드] 항목 수정")
def update_item(item_id: int, data: ItemUpdate, service: ItemServiceDep):
    return service.update(item_id, data)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT, summary="[샘플 코드] 항목 삭제")
def delete_item(item_id: int, service: ItemServiceDep) -> None:
    service.delete(item_id)
