from typing import Any, TypeVar, Type

T = TypeVar("T")


class MetadataMCS(type):
    metadata: dict[str, Any]

    def __or__(cls, other: "Metadata | Type[Metadata]") -> "Metadata | NotImplemented":
        if not isinstance(other, Metadata) and (not isinstance(other, type) or not issubclass(other, Metadata)):
            print("NOT IMPLEMENTED")
            return NotImplemented

        return AggregateMetadata(cls.metadata | other.metadata)

    def __repr__(cls):
        rpr = [f"<metadata {cls.__name__}"]
        if getattr(cls, "metadata", None):
            rpr.append(f" {', '.join(f'{k}={v}' for k, v in cls.metadata.items())}")

        rpr.append(">")
        return "".join(rpr)


class Metadata(metaclass=MetadataMCS):
    metadata: dict[str, Any]

    def __contains__(self, key: str) -> bool:
        return key in self.metadata

    def __or__(self, other: "Metadata") -> "Metadata | NotImplemented":
        if not isinstance(other, Metadata):
            return NotImplemented

        return AggregateMetadata(self.metadata | other.metadata)

    def __repr__(self):
        return f"{type(self).__name__}({', '.join(f'{k}={v}' for k, v in self.metadata.items())})"

    def __init_subclass__(cls, **kwargs):
        cls.metadata = kwargs

    def get(self, key: str, default: T = None) -> T:
        return self.metadata.get(key, default)


def create_metadata_type(name: str, /, **kwargs) -> MetadataMCS:
    return MetadataMCS(name, (Metadata,), {}, **kwargs)


class AggregateMetadata(Metadata):

    def __init__(self, metadata: dict[str, Any]) -> None:
        self.metadata = metadata

    def __or__(self, other: "Metadata | Type[Metadata]") -> "Metadata | NotImplemented":
        if not isinstance(other, Metadata) and (not isinstance(other, type) and not issubclass(other, Metadata)):
            return NotImplemented

        self.metadata |= other.metadata
        return self


Auto = create_metadata_type("Auto", auto=True)
Key = create_metadata_type("Key", key=True)
