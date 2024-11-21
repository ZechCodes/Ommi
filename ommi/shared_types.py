from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ommi.models import OmmiModel


type DBModel = "Any | OmmiModel"
