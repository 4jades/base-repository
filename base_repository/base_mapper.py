from abc import ABC, abstractmethod
from typing import Any

class BaseMapper(ABC):
    """
    Mapping interface between ORM objects and Domain objects (Pydantic schemas).
    """

    @abstractmethod
    def to_domain(self, orm_object: Any) -> Any:
        """Converts an ORM object into a Domain object."""
        raise NotImplementedError()

    @abstractmethod
    def to_orm(self, domain_object: Any) -> Any:
        """Converts a Domain object into an ORM object."""
        raise NotImplementedError()
