import dataclasses
from typing import Annotated

from ommi.field_metadata import create_metadata_flag, StoreAs, Key
from ommi.model_collections import ModelCollection
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

    assert "foo" in TestModel.__ommi_metadata__.fields
    assert TestModel.__ommi_metadata__.fields["foo"].matches(MetadataFlag)


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
