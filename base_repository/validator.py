from collections.abc import Mapping

from pydantic import BaseModel


def validate_config_from_attributes_true(schema: type[BaseModel]) -> bool:
    conf = getattr(schema, "model_config", None)
    if conf is None:
        return False
    if isinstance(conf, Mapping):
        return bool(conf.get("from_attributes", False))
    return bool(getattr(conf, "from_attributes", False))


def validate_schema_base(schema: type[BaseModel]) -> None:
    if not issubclass(schema, BaseModel):
        raise TypeError("mapping_schema must be a subclass of pydantic.BaseModel.")
    if not validate_config_from_attributes_true(schema):
        raise TypeError("mapping_schema.model_config.from_attributes must be set to True.")
