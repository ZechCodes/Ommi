from dataclasses import dataclass
from typing import Annotated
from unittest.mock import MagicMock, AsyncMock, Mock

import pytest
from tramp.results import Result

from ommi import ommi_model
from ommi.drivers.drivers import AbstractDatabaseDriver
from ommi.models.field_metadata import ReferenceTo
from ommi.models.query_fields import LazyLoadTheRelated, LazyLoadEveryRelated
from ommi.query_ast import search


@ommi_model
@dataclass
class ModelA:
    id: int

@ommi_model
@dataclass
class ModelB:
    id: int
    a_id: Annotated[int, ReferenceTo(ModelA)]


a = ModelA(id=1)


@pytest.mark.asyncio
@pytest.mark.parametrize("loader", [LazyLoadTheRelated, LazyLoadEveryRelated])
async def test_load_relation(loader):
    driver_mock = MagicMock(
        spec=AbstractDatabaseDriver,
        find=Mock(return_value=AsyncMock()),
    )

    relation = loader(search(ModelB.a_id == a.id), driver=driver_mock)
    result = await relation.result
    driver_mock.find.assert_called_with(ModelB.a_id == a.id)

    assert isinstance(result, Result.Value)

    await relation.value
    assert await relation.get("default") != "default"
    driver_mock.find.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("loader", [LazyLoadTheRelated, LazyLoadEveryRelated])
async def test_load_relation_fails(loader):
    driver_mock = MagicMock(
        spec=AbstractDatabaseDriver,
        find=Mock(side_effect=Exception("Error")),
    )

    relation = loader(search(ModelB.a_id == a.id), driver=driver_mock)
    result = await relation.result
    driver_mock.find.assert_called_with(ModelB.a_id == a.id)

    assert isinstance(result, Result.Error)

    assert await relation.get("default") == "default"

    with pytest.raises(Exception):
        await relation.value

    assert driver_mock.find.call_count == 3
