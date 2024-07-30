from io import StringIO
from typing import Any, Dict, Optional

from flopy4.block import MFBlocks
from flopy4.model import MFModels
from flopy4.package import MFPackages


class MFSimulation:
    """
    MF6 simulation.
    """

    def __init__(
        self,
        name: Optional[str] = None,
        blocks: Optional[MFBlocks | Dict] = None,
        models: Optional[MFModels | Dict] = None,
        packages: Optional[MFPackages | Dict] = None
    ):
        self.name = name
        self.blocks = MFBlocks(blocks)
        self.options = (
            type(self).blocks.options
            if self.blocks is None
            else self.blocks.options
        )
        self.models = MFModels(models)
        self.packages = MFPackages(packages)

    def __getattribute__(self, name: str) -> Any:
        self_type = type(self)

        if name in self_type.blocks:
            return self[name].value

        if name in self_type.options:
            return self.options[name].value
        
        if name in self_type.models:
            return self.models[name].value
        
        if name in self_type.packages:
            return self.packages[name].value

        return super().__getattribute__(name)

    def __str__(self):
        buffer = StringIO()
        self.write(buffer)
        return buffer.getvalue()

    def __eq__(self, other):
        return super().__eq__(other)
    