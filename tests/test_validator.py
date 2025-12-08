from __future__ import annotations

from pydantic import BaseModel, ConfigDict
import pytest

from base_repository.validator import validate_config_from_attributes_true, validate_schema_base


# Mapping-style configs (ConfigDict behaves like a mapping)
class MappingConfigTrueSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class MappingConfigFalseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=False)


# Helpers for testing the "non-mapping object" branch safely
class _ObjConfig:
    def __init__(self, from_attributes: bool) -> None:
        self.from_attributes = from_attributes


# Fake schema types (not BaseModel) to avoid Pydantic construction constraints
class ObjConfigTrueFakeSchema:
    model_config = _ObjConfig(True)


class ObjConfigFalseFakeSchema:
    model_config = _ObjConfig(False)


class NotBaseModel:
    model_config = ConfigDict(from_attributes=True)


def test_validate_config_from_attributes_true__missing_model_config_returns_false() -> None:
    """
    < validate_config_from_attributes_true returns False when model_config is missing >
    1. Create a type with no `model_config` attribute.
    2. Call validate_config_from_attributes_true(Temp).
    3. Assert it returns False.
    """
    # 1
    Temp = type("Temp", (), {})

    # 2
    out = validate_config_from_attributes_true(Temp)  # type: ignore[arg-type]

    # 3
    assert out is False


def test_validate_config_from_attributes_true__mapping_true() -> None:
    """
    < validate_config_from_attributes_true returns True for mapping config with from_attributes=True >
    1. Use a BaseModel subclass with model_config(from_attributes=True).
    2. Call validate_config_from_attributes_true(schema).
    3. Assert it returns True.
    """
    # 1
    schema = MappingConfigTrueSchema

    # 2
    out = validate_config_from_attributes_true(schema)

    # 3
    assert out is True


def test_validate_config_from_attributes_true__mapping_false() -> None:
    """
    < validate_config_from_attributes_true returns False for mapping config with from_attributes=False >
    1. Use a BaseModel subclass with model_config(from_attributes=False).
    2. Call validate_config_from_attributes_true(schema).
    3. Assert it returns False.
    """
    # 1
    schema = MappingConfigFalseSchema

    # 2
    out = validate_config_from_attributes_true(schema)

    # 3
    assert out is False


def test_validate_config_from_attributes_true__object_true() -> None:
    """
    < validate_config_from_attributes_true returns True for object config with from_attributes=True >
    1. Use a non-BaseModel type whose model_config is an object with from_attributes=True.
    2. Call validate_config_from_attributes_true(schema).
    3. Assert it returns True.
    """
    # 1
    schema = ObjConfigTrueFakeSchema

    # 2
    out = validate_config_from_attributes_true(schema)  # type: ignore[arg-type]

    # 3
    assert out is True


def test_validate_config_from_attributes_true__object_false() -> None:
    """
    < validate_config_from_attributes_true returns False for object config with from_attributes=False >
    1. Use a non-BaseModel type whose model_config is an object with from_attributes=False.
    2. Call validate_config_from_attributes_true(schema).
    3. Assert it returns False.
    """
    # 1
    schema = ObjConfigFalseFakeSchema

    # 2
    out = validate_config_from_attributes_true(schema)  # type: ignore[arg-type]

    # 3
    assert out is False


def test_validate_schema_base__not_subclass_of_base_model_raises() -> None:
    """
    < validate_schema_base raises if mapping_schema is not a BaseModel subclass >
    1. Use a type that is not a subclass of pydantic.BaseModel.
    2. Call validate_schema_base(type).
    3. Assert it raises TypeError with the expected message.
    """
    # 1
    schema = NotBaseModel

    # 2
    # 3
    with pytest.raises(TypeError, match=r"mapping_schema must be a subclass of pydantic\.BaseModel\."):
        validate_schema_base(schema)  # type: ignore[arg-type]


def test_validate_schema_base__from_attributes_not_true_raises() -> None:
    """
    < validate_schema_base raises if model_config.from_attributes is not True >
    1. Use a BaseModel subclass with from_attributes=False.
    2. Call validate_schema_base(schema).
    3. Assert it raises TypeError with the expected message.
    """
    # 1
    schema = MappingConfigFalseSchema

    # 2
    # 3
    with pytest.raises(TypeError, match=r"mapping_schema\.model_config\.from_attributes must be set to True\."):
        validate_schema_base(schema)


def test_validate_schema_base__ok() -> None:
    """
    < validate_schema_base succeeds for BaseModel subclass with from_attributes=True >
    1. Use a BaseModel subclass with from_attributes=True.
    2. Call validate_schema_base(schema).
    3. Assert it does not raise.
    """
    # 1
    schema = MappingConfigTrueSchema

    # 2
    validate_schema_base(schema)

    # 3
    assert True
