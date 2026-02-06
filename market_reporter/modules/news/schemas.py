from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator


class NewsSourceView(BaseModel):
    source_id: str
    name: str
    category: str
    url: str
    enabled: bool


class NewsSourceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=60)
    url: str = Field(min_length=8, max_length=500)
    enabled: bool = True


class NewsSourceUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    category: Optional[str] = Field(default=None, min_length=1, max_length=60)
    url: Optional[str] = Field(default=None, min_length=8, max_length=500)
    enabled: Optional[bool] = None

    @model_validator(mode="after")
    def ensure_any_field(self) -> "NewsSourceUpdateRequest":
        if self.name is None and self.category is None and self.url is None and self.enabled is None:
            raise ValueError("At least one field must be provided")
        return self


class NewsFeedSourceOptionView(BaseModel):
    source_id: str
    name: str
    enabled: bool


class NewsFeedItem(BaseModel):
    source_id: str
    source_name: str
    category: str
    title: str
    link: str = ""
    published: str = ""
    fetched_at: datetime


class NewsFeedResponse(BaseModel):
    items: List[NewsFeedItem]
    warnings: List[str] = Field(default_factory=list)
    selected_source_id: str
