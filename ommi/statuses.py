from typing import Generic, Type, TypeVar

from tramp.results import Value, Nothing


V = TypeVar("V")


class DatabaseStatus(Generic[V]):
    Success: "Type[DatabaseSuccessStatus[V]]"
    Exception: "Type[DatabaseExceptionStatus[V]]"


class DatabaseSuccessStatus(Value, DatabaseStatus):
    def __eq__(self, other):
        if not isinstance(other, DatabaseStatus):
            return NotImplemented

        if not isinstance(other, DatabaseSuccessStatus):
            return False

        return self.value == other.value

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.value!r})"


class DatabaseExceptionStatus(DatabaseStatus, Nothing):
    __match_args__ = ("exception",)

    def __new__(cls, *_):
        return object.__new__(cls)

    def __init__(self, exception: Exception) -> None:
        self.exception = exception

    def __eq__(self, other):
        if not isinstance(other, DatabaseStatus):
            raise NotImplementedError()

        if not isinstance(other, DatabaseExceptionStatus):
            return False

        return True

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.exception!r})"


DatabaseStatus.Success = DatabaseSuccessStatus
DatabaseStatus.Exception = DatabaseExceptionStatus
