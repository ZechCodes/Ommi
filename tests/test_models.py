import dataclasses
from typing import Annotated

from ommi.models.field_metadata import create_metadata_flag, StoreAs, Key, ReferenceTo
from ommi.models.collections import ModelCollection
from ommi.models import ommi_model, OmmiModel
import attrs
import pydantic

from ommi.query_ast import ASTReferenceNode


MetadataFlag = create_metadata_flag("MetadataFlag")


def test_attrs_model():
    @ommi_model
    @attrs.define
    class TestModel(OmmiModel):
        foo: int
        bar: str = attrs.field(default="Default")

    assert isinstance(TestModel.foo, ASTReferenceNode)
    assert isinstance(TestModel.bar, ASTReferenceNode)

    instance = TestModel(foo=1)
    assert instance.foo == 1
    assert instance.bar == "Default"


def test_dataclass_model():
    @ommi_model
    @dataclasses.dataclass
    class TestModel:
        foo: int
        bar: str = dataclasses.field(default="Default")

    assert isinstance(TestModel.foo, ASTReferenceNode)
    assert isinstance(TestModel.bar, ASTReferenceNode)

    instance = TestModel(foo=1)
    assert instance.foo == 1
    assert instance.bar == "Default"


def test_pydantic_model():
    @ommi_model
    class TestModel(pydantic.BaseModel):
        foo: int
        bar: str = "Default"

    assert isinstance(TestModel.foo, ASTReferenceNode)
    assert isinstance(TestModel.bar, ASTReferenceNode)

    instance = TestModel(foo=1)
    assert instance.foo == 1
    assert instance.bar == "Default"


def test_field_metadata():
    @ommi_model
    class TestModel(pydantic.BaseModel):
        foo: Annotated[int, MetadataFlag]
        bar: str = "Default"

    assert "foo" in TestModel.__ommi__.fields
    assert TestModel.__ommi__.fields["foo"].matches(MetadataFlag)


def test_primary_key_first_field():
    @ommi_model(collection=ModelCollection())
    @dataclasses.dataclass
    class Model:
        name: str
        occupation: str

    assert Model.get_primary_key_field().get("field_name") == "name"


def test_primary_key_first_int_field():
    @ommi_model(collection=ModelCollection())
    @dataclasses.dataclass
    class Model:
        name: str
        model_id: int

    assert Model.get_primary_key_field().get("field_name") == "model_id"


def test_primary_key_first_store_as_id():
    @ommi_model(collection=ModelCollection())
    @dataclasses.dataclass
    class Model:
        name: str
        model_id: Annotated[int, StoreAs("_id")]

    assert Model.get_primary_key_field().get("field_name") == "model_id"


def test_primary_key_annotation():
    @ommi_model(collection=ModelCollection())
    @dataclasses.dataclass
    class Model:
        name: str
        model_id: Annotated[str, Key]

    assert Model.get_primary_key_field().get("field_name") == "model_id"


def test_primary_key_named_id():
    @ommi_model(collection=ModelCollection())
    @dataclasses.dataclass
    class Model:
        name: str
        id: str

    assert Model.get_primary_key_field().get("field_name") == "id"


def test_reference_fields():
    collection = ModelCollection()

    @ommi_model(collection=collection)
    @dataclasses.dataclass
    class ModelA:
        id: Annotated[int, StoreAs("_id")]

    @ommi_model(collection=collection)
    @dataclasses.dataclass
    class ModelB:
        model_a_id: Annotated[str, ReferenceTo(ModelA.id)]

    reference = ModelB.__ommi__.references[ModelA][0]
    assert reference.from_model == ModelB
    assert reference.to_model == ModelA
    assert reference.from_field == ModelB.__ommi__.fields["model_a_id"]
    assert reference.to_field == ModelA.__ommi__.fields["id"]


circular_collection = ModelCollection()


@ommi_model(collection=circular_collection)
@dataclasses.dataclass
class CircularModelA:
    id: Annotated[int, StoreAs("_id")]
    model_b_id: Annotated[str, ReferenceTo("CircularModelB.id")]


@ommi_model(collection=circular_collection)
@dataclasses.dataclass
class CircularModelB:
    id: int
    model_a_id: Annotated[str, ReferenceTo(CircularModelA.id)]


def test_circular_references():
    reference = CircularModelA.__ommi__.references[CircularModelB][0]
    assert reference.from_model == CircularModelA
    assert reference.to_model == CircularModelB
    assert reference.from_field == CircularModelA.__ommi__.fields["model_b_id"]
    assert reference.to_field == CircularModelB.__ommi__.fields["id"]

    reference = CircularModelB.__ommi__.references[CircularModelA][0]
    assert reference.from_model == CircularModelB
    assert reference.to_model == CircularModelA
    assert reference.from_field == CircularModelB.__ommi__.fields["model_a_id"]
    assert reference.to_field == CircularModelA.__ommi__.fields["id"]
