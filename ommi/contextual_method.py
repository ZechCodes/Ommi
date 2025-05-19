"""
Contextual Method Decorator for Instance and Class-Level Methods

This module provides a decorator and utility class to manage methods that can
be used at both instance and class levels, ensuring consistent behavior across
contexts.
"""


from types import MethodType
from typing import Callable, ParamSpec, TypeVar

try:
    from typing import Self
except ImportError:
    from typing import Any as Self

P = ParamSpec("P")
R = TypeVar("R")


class ContextualMethod:
    """A descriptor that allows a method to behave differently when called on a class versus an instance.

    This is useful for creating methods that can act as both a regular instance method
    and a class method, depending on the context from which they are called.

    Typically, you would use the `@contextual_method` decorator, which creates an
    instance of this class.

    Example: Example Usage
        ```python
        class MyClass:
            @contextual_method
            def my_method(self, arg):
                print(f"Called on instance {self} with {arg}")

            @my_method.classmethod
            def my_method(cls, arg):
                print(f"Class method variant called on {cls} with {arg}")
        ```
    """
    def __init__(self, method: Callable[P, R]):
        """Initializes the ContextualMethod descriptor.

        Args:
            method: The callable that will serve as the default behavior for both
                    instance and class calls, unless overridden by `classmethod()`.
        """
        self._method = method
        self._classmethod = method

    def classmethod(self, method: Callable[P, R]) -> Self:
        """Decorator to specify a different implementation for when the method is called on the class.

        Args:
            method: The callable to be used when the contextual method is accessed
                    from the class itself (e.g., `MyClass.my_method()`).

        Returns:
            The `ContextualMethod` instance, allowing for fluent interface usage.

        Raises:
            ValueError: If the provided `method` has a different name than the
                        original method this descriptor was initialized with.
        """
        if method.__name__ != self._method.__name__:
            raise ValueError(
                f"Method name {method.__name__!r} does not match {self._method.__name__!r}"
            )

        self._classmethod = method
        return self

    def __get__(self, instance, owner) -> Callable[P, R]:
        """Descriptor protocol method.

        Determines whether to return the instance method or class method variant
        based on whether `instance` is None (indicating a class access).

        Args:
            instance: The instance the method is being accessed from, or None if
                      accessed from the class.
            owner: The class that owns this descriptor.

        Returns:
            A bound method, either to the instance or to the class.
        """
        if instance is None:
            return MethodType(self._classmethod, owner)

        return MethodType(self._method, instance)


def contextual_method(func: Callable[P, R]) -> ContextualMethod:
    """Decorator to create a method that behaves differently on instance vs. class calls.

    This decorator wraps a function, turning it into a `ContextualMethod` descriptor.
    By default, the decorated function will be used for both instance and class calls.

    To specify a different behavior for class calls, you can use the `.classmethod`
    decorator on the result of `@contextual_method`.

    Args:
        func: The function to be decorated. This will be the default implementation
              for instance calls and, initially, for class calls.

    Returns:
        A `ContextualMethod` instance.

    Example:
        ```python
        class MyClass:
            @contextual_method
            def my_method(self, arg):
                print(f"Called on instance {self} with {arg}")

            @my_method.classmethod
            def my_method(cls, arg):
                print(f"Class method variant called on {cls} with {arg}")

        instance = MyClass()
        instance.my_method("test_instance") # Output: Called on instance <...> with test_instance
        MyClass.my_method("test_class")    # Output: Class method variant called on <...> with test_class
        ```
    """
    return ContextualMethod(func)
