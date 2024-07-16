from collections.abc import MutableMapping
from pathlib import Path

from flopy4.block import MFBlock
from flopy4.output import MFOutput
from flopy4.package import MFPackages


class MFModel:
    @property
    def workspace(self) -> Path:
        pass

    @property
    def options(self) -> MFBlock:
        pass

    @property
    def packages(self) -> MFPackages:
        pass

    @property
    def output(self) -> MFOutput:
        pass


class MFModels(MutableMapping):
    def __init__(self, *args, **kwargs):
        self.models = dict()
        self.update(dict(*args, **kwargs))

    def __getitem__(self, key):
        return self.models[self._keytransform(key)]

    def __setitem__(self, key, value):
        self.models[self._keytransform(key)] = value

    def __delitem__(self, key):
        del self.models[self._keytransform(key)]

    def __iter__(self):
        return iter(self.models)

    def __len__(self):
        return len(self.models)
