from pathlib import Path

from flopy4.model import MFModels


class MFSimulation:
    @property
    def workspace(self) -> Path:
        pass

    @property
    def models(self) -> MFModels:
        pass
