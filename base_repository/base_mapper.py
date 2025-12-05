from abc import ABC, abstractmethod
from typing import Generic
from repo_types import TDomain, TModel

class BaseMapper(ABC, Generic[TModel, TDomain]):
    """
    Mapping interface between ORM objects and Domain objects (Pydantic schemas).
    """

    @abstractmethod
    def to_domain(self, orm_object: TModel) -> TDomain:
        """Converts an ORM object into a Domain object."""
        raise NotImplementedError()

    @abstractmethod
    def to_orm(self, domain_object: TDomain) -> TModel:
        """Converts a Domain object into an ORM object."""
        raise NotImplementedError()
