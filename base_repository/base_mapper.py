from abc import ABC, abstractmethod
from typing import Generic
from .repo_types import TModel, TSchema

class BaseMapper(ABC, Generic[TModel, TSchema]):
    """
    Mapping interface between ORM objects and Domain objects (Pydantic schemas).
    """

    @abstractmethod
    def to_domain(self, orm_object: TModel) -> TSchema:
        """Converts an ORM object into a Domain object."""
        raise NotImplementedError()

    @abstractmethod
    def to_orm(self, domain_object: TSchema) -> TModel:
        """Converts a Domain object into an ORM object."""
        raise NotImplementedError()
