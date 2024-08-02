from abc import ABCMeta
from collections import OrderedDict, UserDict
from io import StringIO
from itertools import groupby
from pathlib import Path
from pprint import pformat
from typing import Any, Dict, Mapping, Optional

import flopy4.idm as idm
from flopy4.block import MFBlock, MFBlocks, get_block
from flopy4.component import MFComponent
from flopy4.param import MFParam, MFParams
from flopy4.utils import strip


def get_package(model_name, pkg_name):
    """
    Select a subclass of `MFPackage` for the given model and
    package name. Raise if the package is unrecognized.
    """

    for cls in idm.get_component_classes():
        name = f"{model_name.title()}{pkg_name.title()}"
        if cls.__name__ == name:
            return cls(name=name)

    raise ValueError(f"Unknown component: {model_name}-{pkg_name}")


class MFPackageMeta(type):
    def __new__(cls, clsname, bases, attrs):
        if clsname == "MFPackage":
            return super().__new__(cls, clsname, bases, attrs)

        # detect package name
        pkg_name = clsname.replace("Package", "")

        # add class attributes for the parameter specification.
        # dynamically set each parameter's name and docstring.
        params = dict()
        for attr_name, attr in attrs.items():
            if issubclass(type(attr), MFParam):
                attr.__doc__ = attr.description
                attr.name = attr_name
                attrs[attr_name] = attr
                params[attr_name] = attr

        # add class attributes for the block specification.
        # subclass `MFBlock` dynamically with name/params
        # as given in the block parameter specification.
        blocks = dict()
        for block_name, block_params in groupby(
            params.values(), lambda p: p.block
        ):
            block = get_block(
                component_name=pkg_name,
                block_name=block_name,
                params={param.name: param for param in block_params},
            )
            attrs[block_name] = block
            blocks[block_name] = block

        attrs["params"] = MFParams(params)
        attrs["blocks"] = MFBlocks(blocks)

        return super().__new__(cls, clsname, bases, attrs)


class MFPackageMappingMeta(MFPackageMeta, ABCMeta):
    # http://www.phyast.pitt.edu/~micheles/python/metatype.html
    pass


class MFPackage(MFBlocks, metaclass=MFPackageMappingMeta):
    """
    MF6 package. Maps block names to blocks.


    Notes
    -----
    Subclasses are generated from Jinja2 templates to
    match models/packages specified in definition files.


    TODO: reimplement with `ChainMap`?
    """

    def __init__(
        self,
        name: Optional[str] = None,
        path: Optional[Path] = None,
        blocks: Optional[Dict] = None,
    ):
        self.name = name
        self.path = path
        super().__init__(blocks=blocks)

    def __getattribute__(self, name: str) -> Any:
        self_type = type(self)

        if name in self_type.blocks:
            return self[name].value

        if name in self_type.params:
            return self._get_param_values()[name]

        if name == "blocks":
            return self.value

        elif name == "params":
            return self._get_param_values()

        return super().__getattribute__(name)

    def __str__(self):
        buffer = StringIO()
        self.write(buffer)
        return buffer.getvalue()

    def __eq__(self, other):
        return super().__eq__(other)

    def _get_params(self) -> Dict[str, MFParam]:
        """Get a flattened dictionary of member parameters."""
        return {
            param_name: param
            for block in self.values()
            for param_name, param in block.items()
        }

    def _get_param_values(self) -> Dict[str, Any]:
        """Get a flattened dictionary of parameter values."""
        return {
            param_name: param.value
            for param_name, param in self._get_params().items()
        }

    @property
    def value(self) -> Dict[str, Dict[str, Any]]:
        """
        Get a dictionary of package block values. This is a
        nested mapping of block names to blocks, where each
        block is a mapping of parameter names to parameter
        values.
        """
        return MFBlocks.value.fget(self)

    @value.setter
    def value(self, value: Optional[Dict[str, Dict[str, Any]]]):
        """
        Set package block values from a nested dictionary,
        where each block value is a mapping of parameter
        names to parameter values.
        """

        if not value:
            return

        blocks = type(self).coerce(value.copy(), set_default=True)
        MFBlocks.value.fset(self, blocks)

    @classmethod
    def coerce(
        cls, blocks: Mapping[str, MFBlock], set_default: bool = False
    ) -> Dict[str, MFBlock]:
        """
        Check that the dictionary contains only known blocks,
        raising an error if any unknown blocks are provided.

        Sets default values for any missing member parameters
        and ensures provided parameter types are as expected.
        """

        known = dict()
        for block_name, block_spec in cls.blocks.copy().items():
            block = blocks.pop(block_name, block_spec)
            block = type(block).coerce(block, set_default=set_default)
            known[block_name] = block

        if any(blocks):
            raise ValueError(f"Unrecognized blocks:\n{pformat(blocks)}")

        return known

    @classmethod
    def load(cls, f, **kwargs):
        """Load the package from file."""
        blocks = dict()
        members = cls.blocks

        while True:
            pos = f.tell()
            line = f.readline()
            if line == "":
                break
            if line == "\n":
                continue
            line = strip(line).lower()
            words = line.split()
            key = words[0]
            if key == "begin":
                name = words[1]
                block = members.get(name, None)
                if block is None:
                    continue
                f.seek(pos)
                blocks[name] = type(block).load(f, **kwargs)

        return cls(blocks=blocks)

    def write(self, f, **kwargs):
        """Write the package to file."""
        super().write(f, **kwargs)


class MFPackages(MFComponent, UserDict):
    """
    Mapping of package names to packages. Acts like a
    dictionary, also supports named attribute access.
    """

    def __init__(self, blocks=None):
        MFPackages.check(blocks)
        super().__init__(blocks)
        for key, block in self.items():
            setattr(self, key, block)

    def __repr__(self):
        return pformat(self.data)

    def __eq__(self, other):
        tother = type(other)
        if issubclass(tother, MFPackages):
            other = other.value
        if issubclass(tother, Mapping):
            return OrderedDict(sorted(self.value)) == OrderedDict(
                sorted(other)
            )
        return False

    @staticmethod
    def check(items):
        """
        Raise if any items are not instances of `MFPackage` or subclasses.
        """
        if not items:
            return
        elif isinstance(items, dict):
            items = items.values()
        not_pkgs = [
            b
            for b in items
            if b is not None and not issubclass(type(b), MFPackage)
        ]
        if any(not_pkgs):
            raise TypeError(f"Expected MFPackage subclasses, got {not_pkgs}")

    @property
    def value(self) -> Dict:
        """
        Get a nested dictionary of package values. This is a
        nested mapping of package names to packages, where
        packages map package names to package values. Each
        package value is itself a nested mapping of blocks,
        each of which maps parameter names to param values.
        """
        return {k: v.value for k, v in self.items()}

    @value.setter
    def value(self, value: Optional[Dict]):
        """Set package values from a nested dictionary."""

        if not value:
            return

        pkgs = value.copy()
        MFPackages.check(pkgs)
        self.update(pkgs)
        for key, pkg in self.items():
            setattr(self, key, pkg)
