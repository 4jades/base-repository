from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ItemSchema(BaseModel):
  model_config = ConfigDict(from_attributes=True)
  id: int | None = None
  name: str



class CategorySchema(BaseModel):
  model_config = ConfigDict(from_attributes=True)
  id: int | None = None
  title: str



class ResultStrictSchema(BaseModel):
  model_config = ConfigDict(from_attributes=True)
  id: int | None = None
  item_id: int
  sub_category_id: int | None
  result_value: str | None
  is_abnormal: bool | None
  tenant_id: int
  checkup_id: int