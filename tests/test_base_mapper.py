from __future__ import annotations

import pytest

from base_repository.base_mapper import BaseMapper



def test_cannot_instantiate_abstract_mapper() -> None:
    """
    < Abstract mapper subclass without method implementations must not be instantiable >
    1. Define a BaseMapper subclass that does not implement abstract methods.
    2. Attempt to instantiate it.
    3. Assert TypeError is raised.
    """
    # 1
    class IncompleteMapper(BaseMapper[int, int]):
        pass

    # 2
    # 3
    with pytest.raises(TypeError):
        _ = IncompleteMapper()



def test_can_instantiate_concrete_mapper_and_methods_work() -> None:
    """
    < Concrete mapper implementing both methods must be instantiable and functional >
    1. Define a BaseMapper subclass implementing to_domain and to_orm.
    2. Instantiate it.
    3. Assert both methods return expected values.
    """
    # 1
    class ConcreteMapper(BaseMapper[int, int]):
        def to_domain(self, orm_object: int) -> int:
            return orm_object + 1

        def to_orm(self, domain_object: int) -> int:
            return domain_object - 1

    # 2
    m = ConcreteMapper()

    # 3
    assert m.to_domain(10) == 11
    assert m.to_orm(11) == 10



def test_calling_super_hits_base_notimplemented_lines() -> None:
    """
    < Calling super() in overridden methods hits BaseMapper NotImplementedError lines >
    1. Define a mapper that overrides methods but delegates to super().
    2. Instantiate it.
    3. Call to_domain and to_orm and assert NotImplementedError is raised.
    """
    # 1
    class SuperCallingMapper(BaseMapper[int, int]):
        def to_domain(self, orm_object: int) -> int:
            return super().to_domain(orm_object)

        def to_orm(self, domain_object: int) -> int:
            return super().to_orm(domain_object)

    # 2
    m = SuperCallingMapper()

    # 3
    with pytest.raises(NotImplementedError):
        _ = m.to_domain(1)

    with pytest.raises(NotImplementedError):
        _ = m.to_orm(1)
