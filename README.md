# Ommi

> [!CAUTION]
> Ommi is under construction and much of the functionality is undergoing frequent revision. There is no guaratee future versions will be backwards compatible.

An object model mapper intended to provide a consistent interface for many underlying database implementations using whatever model implementations are desired.

### Compatible Model Implementations

My test suite checks for compatibility with the following model implementations:

- Python's `dataclass` model types
- [Attrs](https://www.attrs.org/en/stable/comparison.html) model types
- [Pydantic](https://docs.pydantic.dev/latest/) model types

### Included Database Support

- SQLite3 (⚠️Under Construction⚠️)
