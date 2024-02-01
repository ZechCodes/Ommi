from typing import Type

import ommi.models


class ModelCollection:
    def __init__(self):
        self.models = set()

    def add(self, model: "Type[ommi.models.OmmiModel]"):
        self.models.add(model)
