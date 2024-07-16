from abc import ABCMeta
from collections.abc import MutableMapping
from typing import Dict

from flopy4.block import MFBlock, MFBlocks


def get_member_blocks(cls) -> Dict[str, MFBlock]:
    return {
        k: v
        for k, v in cls.__dict__.items()
        if issubclass(type(v), MFBlock) or issubclass(type(v), MFBlocks)
    }


class MFPackageMeta(type):
    def __new__(cls, clsname, bases, attrs):
        # todo: setup hooks to settings data. we want to
        # be able to define a block in terms of MFScalar,
        # MFArray and MFList while returning native types
        # to the user, like what Django does for Models.
        return super().__new__(cls, clsname, bases, attrs)


class MFPackageMappingMeta(MFPackageMeta, ABCMeta):
    # http://www.phyast.pitt.edu/~micheles/python/metatype.html
    pass


class MFPackage(MutableMapping, metaclass=MFPackageMappingMeta):
    def __init__(self, name, *args, **kwargs):
        self._name = name
        self._blocks = dict()
        self.update(dict(*args, **kwargs))

    def __getitem__(self, key):
        return self._blocks[key]

    def __setitem__(self, key, value):
        self._blocks[key] = value

    def __delitem__(self, key):
        del self._blocks[key]

    def __iter__(self):
        return iter(self._blocks)

    def __len__(self):
        return len(self._blocks)

    @property
    def options(self) -> MFBlock:
        return self._blocks["options"]

    @property
    def package(self) -> MFBlock:
        return self._blocks["package"]

    @property
    def periods(self) -> MFBlocks:
        return self._blocks["periods"]


class MFPackages(MutableMapping):
    def __init__(self, *args, **kwargs):
        self.packages = dict()
        self.update(dict(*args, **kwargs))

    def __getitem__(self, key):
        return self.packages[key]

    def __setitem__(self, key, value):
        self.packages[key] = value

    def __delitem__(self, key):
        del self.packages[key]

    def __iter__(self):
        return iter(self.packages)

    def __len__(self):
        return len(self.packages)
