from collections import defaultdict
from dataclasses import dataclass
from typing import Type, Any

from ommi import query_ast
from ommi.models.field_metadata import ReferenceTo, FieldMetadata
import ommi.models


@dataclass
class FieldReference:
    from_model: "Type[ommi.models.OmmiModel]"
    from_field: FieldMetadata
    to_model: "Type[ommi.models.OmmiModel]"
    to_field: FieldMetadata


class LazyReferenceBuilder:
    def __init__(self, fields: dict[str, FieldMetadata], model: "Type[ommi.models.OmmiModel]", namespace: dict[str, Any]):
        self._built = False
        self._fields = fields
        self._model = model
        self._namespace = namespace
        self._references: dict[Type[ommi.models.OmmiModel], list[FieldReference]] = defaultdict(list)

    def __getitem__(self, model: "Type[ommi.models.OmmiModel]") -> list[FieldReference]:
        if not self._built:
            self._build_references()

        return self._references[model]

    def get(self, model: "Type[ommi.models.OmmiModel]", default: list[FieldReference] | None = None) -> list[FieldReference]:
        if not self._built:
            self._build_references()

        return self._references.get(model, default)

    def _build_references(self) -> None:
        for name, metadata in self._fields.items():
            if metadata.matches(ReferenceTo):
                match metadata.get("reference_to"):
                    case query_ast.ASTReferenceNode(to_field, to_model):
                        self._references[to_model].append(
                            FieldReference(
                                from_model=self._model,
                                from_field=metadata,
                                to_model=to_model,
                                to_field=to_field.metadata,
                            )
                        )

                    case str() as ref:
                        reference: query_ast.ASTReferenceNode = eval(ref, vars(self._namespace))
                        self._references[reference.model].append(
                            FieldReference(
                                from_model=self._model,
                                from_field=metadata,
                                to_model=reference.model,
                                to_field=reference.field.metadata,
                            )
                        )

        self._built = True
