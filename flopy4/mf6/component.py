from abc import ABC
from collections.abc import MutableMapping

from xattree import xattree
from flopy4.io import Writer

COMPONENTS = {}
"""MF6 component registry."""


@xattree
class Component(ABC, MutableMapping, Writer):
    @classmethod
    def __attrs_init_subclass__(cls):
        COMPONENTS[cls.__name__.lower()] = cls

    def __getitem__(self, key):
        return self.children[key]  # type: ignore

    def __setitem__(self, key, value):
        self.children[key] = value  # type: ignore

    def __delitem__(self, key):
        del self.children[key]  # type: ignore

    def __iter__(self):
        return iter(self.children)  # type: ignore

    def __len__(self):
        return len(self.children)  # type: ignore
