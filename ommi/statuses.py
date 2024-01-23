from typing import Generic, Type, TypeVar

from tramp.results import Value, Nothing


V = TypeVar("V")


class DatabaseStatus(Generic[V]):
    Success: "Type[DatabaseStatus[V]]"
    Exception: "DatabaseStatus[V]"


class DatabaseSuccessStatus(DatabaseStatus, Value):
    def __eq__(self, other):
        if not isinstance(other, DatabaseStatus):
            return NotImplemented

        if not isinstance(other, DatabaseSuccessStatus):
            return False

        return self.value == other.value

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.value!r})"


class DatabaseExceptionStatus(DatabaseStatus, Nothing):
    def __eq__(self, other):
        if not isinstance(other, DatabaseStatus):
            raise NotImplementedError()

        if not isinstance(other, DatabaseExceptionStatus):
            return False

        return True
