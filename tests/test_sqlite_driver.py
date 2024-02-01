from dataclasses import dataclass

import pytest

from ommi.driver_context import use_driver
from ommi.ext.drivers.sqlite import SQLiteConfig, SQLiteDriver
from ommi.model_collections import ModelCollection
from ommi.models import ommi_model
from ommi.statuses import DatabaseStatus


@pytest.mark.asyncio
async def test_sqlite_driver():
    models = ModelCollection()

    @ommi_model(collection=models)
    @dataclass
    class DummyModel:
        name: str

    with use_driver(SQLiteDriver()) as driver:
        await driver.connect(SQLiteConfig(filename=":memory:")).or_raise()
        await driver.sync_schema(models).or_raise()

        model = DummyModel(name="dummy")
        await model.add()

        result = await driver.fetch(DummyModel.name == "dummy").or_raise()
        assert isinstance(result, DatabaseStatus.Success)
        assert result.value.name == model.name
