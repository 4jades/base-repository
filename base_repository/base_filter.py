from __future__ import annotations

from dataclasses import fields, is_dataclass
from typing import Annotated, Any
from collections.abc import Sequence, Set as ABCSet
from typing_extensions import Doc


class BaseRepoFilter:
    """
    A helper base class that builds SQLAlchemy WHERE criteria from a dataclass.

    How to use
    ----------
    1. Inherit from this class and declare it as a dataclass.
       Example:
           @dataclass
           class UserFilter(BaseRepoFilter):
               id: int | None = None
               name: str | None = None
               is_active: bool | None = None

    2. Call where_criteria(model) to get a list of SQLAlchemy criteria based on field values.
       - None         → no condition generated
       - bool         → col.is_(val)
       - sequence     → col.in_(seq) (empty sequences are ignored)
       - other scalar → col == val

       Examples:
        id=1                   → User.id == 1
        id=[1, 2, 3]           → User.id.in_([1, 2, 3])
        is_active=True         → User.is_active.is_(True)

    Mapping rules
    -------------
    1) Automatic mapping: dataclass field name ↔ model column name
       - Assumes the field name matches the model attribute/column name.

    2) Manual mapping via __aliases__
       - If a field name differs from the column name, define __aliases__ in the subclass.
         Example:
             class UserFilter(BaseRepoFilter):
                 __aliases__ = {"org": "org_id"}  # field org → column org_id

    3) Strict mapping mode: __strict__ = True
       - If the mapped column does not exist on the model, raise ValueError immediately.
       - If False, silently ignore unmapped fields.

    Example
    -------
    >>> @dataclass
    ... class UserFilter(BaseRepoFilter):
    ...     id: int | Sequence[int] | None = None
    ...     name: str | None = None
    ...     is_active: bool | None = None
    ...
    >>> f = UserFilter(id=[1, 2], is_active=True)
    >>> crit = f.where_criteria(User)
    >>> # crit looks like: [User.id.in_([1, 2]), User.is_active.is_(True)]
    """

    __aliases__: Annotated[
        dict[str, str],
        Doc(
            "A mapping dict for field name → column name.\n"
            "Example: {'org': 'org_id'} maps the 'org' field to the model's 'org_id' column."
        ),
    ] = {}

    __strict__: Annotated[
        bool,
        Doc(
            "Strict mapping mode flag.\n"
            "- True  : raise ValueError if a field cannot be mapped to a model column.\n"
            "- False : silently ignore unmapped fields."
        ),
    ] = False

    # ------------------------------------------------------------------ #
    # Internal utilities                                                  #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _is_seq(
        value: Annotated[Any, Doc("Value to check for sequence-ness (expects list/tuple/set/frozenset, etc.).")],
    ) -> Annotated[bool, Doc("True if value is a supported sequence type, otherwise False.")]:
        """
        Check whether the value is a Sequence or Set-like object.
        Note: str/bytes/bytearray are excluded.
        """
        # Exclude string-like types (they are Sequence but not suitable for IN)
        if isinstance(value, (str, bytes, bytearray)):
            return False

        return isinstance(value, (Sequence, ABCSet))

    @classmethod
    def _resolve_column_name(
        cls,
        field_name: Annotated[str, Doc("Dataclass field name.")],
    ) -> Annotated[str, Doc("Resolved column name to use for mapping.")]:
        """
        Resolve the actual model column name for a given field name.

        Rules
        -----
        1) If defined in __aliases__: use that value
        2) Otherwise: use the original field name
        """
        if field_name in cls.__aliases__:
            return cls.__aliases__[field_name]

        return field_name

    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #

    def where_criteria(
        self,
        m: Annotated[type[Any], Doc("SQLAlchemy ORM model class.")],
    ) -> Annotated[list[Any], Doc("A list of SQLAlchemy criteria for a WHERE clause.")]:
        """
        Build SQLAlchemy WHERE criteria based on dataclass field values.

        Behavior
        --------
        1) Validate that `self` is a dataclass. (TypeError if not)
        2) Iterate over dataclass fields and for each one:
           - Skip if the value is None
           - Resolve column name via _resolve_column_name(field_name)
           - If the model does not have the column:
               - If __strict__ is True: raise ValueError
               - Otherwise: ignore the field
           - Generate criteria based on value type:
               * bool           → col.is_(val)
               * sequence       → if non-empty: col.in_(seq)
               * other scalar   → col == val

        Parameters
        ----------
        m:
            Target SQLAlchemy model class to build WHERE criteria against.

        Returns
        -------
        list[Any]
            A list of SQLAlchemy criteria objects, e.g. [User.id == 1, User.is_active.is_(True)]

        Raises
        ------
        TypeError
            If `self` is not a dataclass.
        ValueError
            If __strict__ = True and the mapped column cannot be found on the model.
        """
        if not is_dataclass(self):
            raise TypeError("BaseRepoFilter must be used with a dataclass.")

        crit: list[Any] = []
        for f in fields(self):
            val = getattr(self, f.name)
            if val is None:
                continue

            col_name = self._resolve_column_name(f.name)
            col = getattr(m, col_name, None)

            if col is None:
                if self.__strict__:
                    raise ValueError(f"Mapping failed: {m.__name__}.{col_name} (from '{f.name}')")
                continue

            if isinstance(val, bool):
                # Use .is_(val) for bool values to represent NULL/True/False precisely
                crit.append(col.is_(val))
            elif self._is_seq(val):
                # Build an IN condition for sequences; ignore empty sequences
                seq = list(val)
                if seq:
                    crit.append(col.in_(seq))
            else:
                # For other scalar values, use ==
                crit.append(col == val)

        return crit
