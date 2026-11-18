from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Message(BaseModel):
    detail: str


class PageMeta(BaseModel):
    page: int
    page_size: int
    total: int
    pages: int


class Page(BaseModel, Generic[T]):
    items: List[T]
    meta: PageMeta


class PaginationParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(10, ge=1, le=100)
    sort_by: Optional[str] = None
    sort_dir: str = Field("asc", pattern="^(asc|desc)$")


def paginate(query, page: int, page_size: int):
    total = query.order_by(None).count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    pages = (total + page_size - 1) // page_size if page_size else 0
    return items, PageMeta(page=page, page_size=page_size, total=total, pages=pages)
