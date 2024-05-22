from typing import Type

import ommi.models


class ModelCollection:
    def __init__(self):
        self.models = set()

    def add(self, model: "Type[ommi.models.OmmiModel]"):
        self.models.add(model)

    def __repr__(self):
        return f"<{type(self).__name__}: contains {len(self.models)} model{'' if len(self.models) == 1 else 's'}>"
