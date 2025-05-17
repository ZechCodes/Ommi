from abc import ABC, abstractmethod
from typing import Awaitable, Callable, Type


class DBStatusNoResultException(Exception):
    pass


class DBResult[T](ABC):
    __match_args__ = ("result", "exception")

    DBSuccess: "Type[DBSuccess[T]]"
    DBFailure: "Type[DBFailure[T]]"

    def __init_subclass__(cls, **kwargs):
        if cls.__name__ in DBResult.__annotations__:
            setattr(DBResult, cls.__name__, cls)

    @property
    @abstractmethod
    def result(self) -> T:
        ...

    @property
    @abstractmethod
    def exception(self) -> Exception:
        ...

    @abstractmethod
    def result_or[D](self, default: D) -> T | D:
        ...

    @abstractmethod
    def exception_or[D](self, default: D) -> Exception | D:
        ...

    @classmethod
    def build[**P](cls, callback: Callable[P, Awaitable[T]], *args: P.args, **kwargs: P.kwargs) -> "DBResultBuilder[T]":
        return DBResultBuilder(callback, *args, **kwargs)


class DBSuccess[T](DBResult[T]):
    __match_args__ = ("result",)

    def __init__(self, result: T):
        self._result = result

    @property
    def exception(self) -> Exception:
        raise DBStatusNoResultException("DBResult does not wrap an exception")

    @property
    def result(self) -> T:
        return self._result

    def result_or[D](self, default: D) -> T | D:
        return self._result

    def exception_or[D](self, default: D) -> D:
        return default


class DBFailure[T](DBResult[T]):
    __match_args__ = ("exception",)

    def __init__(self, exception: Exception):
        self._exception = exception

    @property
    def exception(self) -> Exception:
        return self._exception

    @property
    def result(self) -> T:
        raise DBStatusNoResultException("DBResult does not wrap a result")

    def result_or[D](self, default: D) -> D:
        return default

    def exception_or[D](self, default: D) -> Exception:
        return self._exception


class DBResultBuilder[T]:
    def __init__(self, callback: Callable, *args, **kwargs):
        self._callback = callback
        self._args = args
        self._kwargs = kwargs

    def __await__(self):
        return self._get().__await__()

    async def or_raise(self) -> T:
        return await self._callback(*self._args, **self._kwargs)

    async def _get(self) -> DBResult[T]:
        try:
            return DBResult.DBSuccess(await self.or_raise())
        except Exception as e:
            return DBResult.DBFailure(e)
