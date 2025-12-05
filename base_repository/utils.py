import functools
import warnings

from collections.abc import Callable
from typing import Any, TypeVar, cast

F = TypeVar("F", bound=Callable[..., Any])


def experimental(func: F) -> F:
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        warnings.warn(
            f"{func.__name__}() is experimental and may change or be removed in a future release.",
            category=UserWarning,
            stacklevel=2,
        )
        return func(*args, **kwargs)

    return cast(F, wrapper)
