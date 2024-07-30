from collections import UserDict, OrderedDict
from io import StringIO
from itertools import groupby
from pprint import pformat
from typing import Any, Dict, Mapping, Optional

from flopy4.block import MFBlocks, get_block
from flopy4.package import MFPackage, MFPackages, get_package
from flopy4.param import MFParam, MFParams
from flopy4.utils import strip


class MFModelMeta(type):
    def __new__(cls, clsname, bases, attrs):
        if clsname == "MFModel":
            return super().__new__(cls, clsname, bases, attrs)

        # detect package name
        model_name = clsname.replace("Model", "")

        # add class attributes for the parameter specification.
        # dynamically set each parameter's name and docstring.
        params = dict()
        for attr_name, attr in attrs.items():
            if issubclass(type(attr), MFParam):
                attr.__doc__ = attr.description
                attr.name = attr_name
                attrs[attr_name] = attr
                params[attr_name] = attr

        # add class attributes for the block specification
        # and the package specification. subclass `MFBlock`
        # dynamically with name/params matching block spec.
        # find the `MFPackage` subclass in the idm module.
        blocks = dict()
        packages = dict()
        for block_name, block_params in groupby(
            params.values(), lambda p: p.block
        ):
            params_map = {param.name: param for param in block_params}
            block = get_block(
                component_name=model_name,
                block_name=block_name,
                params=params_map,
            )
            attrs[block_name] = block
            blocks[block_name] = block

            if block_name == "packages":
                pkgs = params_map.get("packages")
                for pkg_record in pkgs:
                    pkg_name = pkg_record.name
                    package = get_package(
                        model_name=model_name, pkg_name=pkg_name
                    )
                    attrs[pkg_name] = package
                    packages[pkg_name] = package

        attrs["params"] = MFParams(params)
        attrs["blocks"] = MFBlocks(blocks)
        attrs["packages"] = MFPackages(packages)

        return super().__new__(cls, clsname, bases, attrs)


class MFModel(metaclass=MFModelMeta):
    """
    MF6 model.


    Notes
    -----
    Subclasses are generated from Jinja2 templates to
    match models/packages specified in definition files.
    """

    def __init__(
        self,
        name: Optional[str] = None,
        blocks: Optional[MFBlocks | Dict] = None,
        packages: Optional[MFPackages | Dict] = None,
    ):
        self.name = name
        self.blocks = MFBlocks(blocks)
        self.options = (
            type(self).blocks.options
            if self.blocks is None
            else self.blocks.options
        )
        self.packages = MFPackages(packages)

    def __getattribute__(self, name: str) -> Any:
        self_type = type(self)

        if name in self_type.blocks:
            return self[name].value

        if name in self_type.options:
            return self.options[name].value
        
        if name in self_type.packages:
            return self.packages[name].value

        return super().__getattribute__(name)

    def __str__(self):
        buffer = StringIO()
        self.write(buffer)
        return buffer.getvalue()

    def __eq__(self, other):
        return super().__eq__(other)

    @classmethod
    def coerce(
        cls, packages: Mapping[str, MFPackage], set_default: bool = False
    ) -> Dict[str, MFPackage]:
        """
        Check that the dictionary contains only known packages,
        raising an error if any unknown packages are provided.

        Sets default values for any missing member parameters
        and ensures provided parameter types are as expected.
        """

        known = dict()
        for pkg_name, pkg_spec in cls.packages.copy().items():
            pkg = packages.pop(pkg_name, pkg_spec)
            pkg = type(pkg).coerce(pkg, set_default=set_default)
            known[pkg_name] = pkg

        if any(packages):
            raise ValueError(f"Unrecognized packages:\n{pformat(packages)}")

        return known

    @classmethod
    def load(cls, f, **kwargs):
        """Load the model from file."""
        blocks = dict()
        packages = dict()
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
                block_name = words[1]
                block = members.get(block_name, None)
                if block is None:
                    continue
                f.seek(pos)
                blocks[block_name] = type(block).load(f, **kwargs)
                if block_name != "packages":
                    continue
                for pkg_record in block["packages"]:
                    pkg_name = pkg_record.name
                    package = get_package(
                        model_name=block_name, pkg_name=pkg_name
                    )
                    packages[pkg_name] = package

        return cls(blocks=blocks, packages=packages)

    def write(self, f, **kwargs):
        """Write the model to file."""

        for block in self.blocks.values():
            block.write(f, **kwargs)

        for package in self.packages.values():
            with open(package.path, "w") as pf:
                package.write(pf, **kwargs)


class MFModels(UserDict):
    """
    Mapping of model names to models. Acts like a
    dictionary, also supports named attribute access.
    """

    def __init__(self, models=None):
        MFModels.check(models)
        super().__init__(models)
        for key, model in self.items():
            setattr(self, key, model)

    def __repr__(self):
        return pformat(self.data)

    def __eq__(self, other):
        tother = type(other)
        if issubclass(tother, MFModels):
            other = other.value
        if issubclass(tother, Mapping):
            return OrderedDict(sorted(self.value)) == OrderedDict(
                sorted(other)
            )
        return False
    
    @staticmethod
    def check(items):
        """
        Raise if any items are not instances of `MFModel` or subclasses.
        """
        if not items:
            return
        elif isinstance(items, dict):
            items = items.values()
        not_pkgs = [
            b
            for b in items
            if b is not None and not issubclass(type(b), MFModel)
        ]
        if any(not_pkgs):
            raise TypeError(f"Expected MFModel subclasses, got {not_pkgs}")

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
        MFModels.check(pkgs)
        self.update(pkgs)
        for key, pkg in self.items():
            setattr(self, key, pkg)