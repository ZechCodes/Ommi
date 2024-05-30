from dataclasses import dataclass, field as dc_field

from ommi.models.collections import get_global_collection
from ommi.models.references import LazyReferenceBuilder
import ommi.models.collections


@dataclass
class OmmiMetadata:
    model_name: str
    fields: "dict[str, ommi.models.field_metadata.FieldMetadata]"
    references: LazyReferenceBuilder
    collection: "ommi.models.collections.ModelCollection" = dc_field(
        default_factory=get_global_collection
    )

    def clone(self, **kwargs) -> "OmmiMetadata":
        return OmmiMetadata(
            **{name: kwargs.get(name, value) for name, value in vars(self).items()}
        )
