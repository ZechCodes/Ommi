from typing import TypeVar, Iterable

T = TypeVar("T")


def first(iterable: Iterable[T], default: T | None = None) -> T | None:
    return next(iter(iterable), default)
