from abc import ABC
from collections.abc import MutableMapping

from xattree import xattree

from flopy4.mf6.io import ComponentReader, ComponentWriter, IOMethod

COMPONENTS = {}
"""MF6 component registry."""


@xattree
class Component(ABC, MutableMapping):
    """
    Base class for MF6 components.

    We use the `children` attribute provided by `xattree`. We know
    children are also `Component`s, but mypy does not. How to fix?
    """

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

    _read = IOMethod(ComponentReader)  # type: ignore
    _write = IOMethod(ComponentWriter)  # type: ignore

    def read(self, format=None) -> None:
        self._read(format=format)
        for child in self.children.values():  # type: ignore
            child.read(format=format)

    def write(self, format=None) -> None:
        self._write(format=format)
        for child in self.children.values():  # type: ignore
            child.write(format=format)
