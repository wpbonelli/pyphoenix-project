from abc import ABCMeta
from collections import OrderedDict, UserDict
from dataclasses import asdict
from io import StringIO
from pprint import pformat
from typing import Any, Dict, Mapping, Optional

from flopy4.array import MFArray
from flopy4.compound import MFKeystring, MFRecord, get_keystrings
from flopy4.context import SimContext
from flopy4.param import MFParam, MFParams, MFParamSpec
from flopy4.scalar import MFScalar
from flopy4.utils import strip, uppers


def get_block(component_name, block_name, params):
    """
    Dynamically subclass `MFBlock`. The class' name is composed from
    the given package and block name. The class will have attributes
    according to the given parameter specification; parameter values
    are not yet initialized.
    """
    cls = MFBlockMeta(
        f"{component_name.title()}{block_name.title()}Block",
        (MFBlock,),
        params.copy(),
    )
    return cls(name=block_name, params=params)


def get_param(params, block_name, param_name):
    """
    Find the first parameter in the collection with
    the given name, set its block name, and return it.
    """
    param = next(get_keystrings(params, param_name), None)
    if param is None:
        param = params.get(param_name)
        if param is None:
            raise ValueError(f"Invalid parameter: {param_name}")
        param.name = param_name
    param.block = block_name
    return param


class MFBlockMeta(type):
    def __new__(cls, clsname, bases, attrs):
        if clsname == "MFBlock":
            return super().__new__(cls, clsname, bases, attrs)

        # detect block name
        block_name = (
            clsname[list(uppers(clsname))[1] :].replace("Block", "").lower()
        )

        # add class attributes for the block parameter specification.
        # dynamically set each parameter's name, block and docstring.
        params = dict()
        for attr_name, attr in attrs.items():
            if issubclass(type(attr), MFParam):
                attr.__doc__ = attr.description
                attr.name = attr_name
                attr.block = block_name
                attrs[attr_name] = attr
                params[attr_name] = attr

        attrs["params"] = MFParams(params)

        return super().__new__(cls, clsname, bases, attrs)


class MFBlockMappingMeta(MFBlockMeta, ABCMeta):
    # http://www.phyast.pitt.edu/~micheles/python/metatype.html
    pass


class MFBlock(MFParams, metaclass=MFBlockMappingMeta):
    """
    MF6 input block. Maps parameter names to parameters.


    Notes
    -----
    This class is dynamically subclassed by `MFPackage`
    to match each block within a package parameter set.

    Supports dictionary and attribute access. The class
    attributes specify the block's parameters. Instance
    attributes expose the parameter value.

    The block's name and index are discovered upon load.
    Likewise the parameter values are populated on load.
    They can also be initialized by passing a dictionary
    of names/values to `params` when calling `__init__`.
    Only recognized parameters (i.e. parameters known to
    the block specification) are allowed.
    """

    def __init__(
        self,
        name: Optional[str] = None,
        index: Optional[int] = None,
        params: Optional[Dict] = None,
    ):
        self.name = name
        self.index = index

        # if a parameter mapping is provided, coerce it to the
        # spec and set default values
        if params is not None:
            params = type(self).coerce(params, set_default=True)

        super().__init__(params=params)

    def __getattribute__(self, name: str) -> Any:
        self_type = type(self)

        # shortcut to parameter value for instance attribute.
        # the class attribute is the parameter specification.
        if name in self_type.params:
            return self.value[name]

        # add .params attribute as an alias for .value, this
        # overrides the class attribute with the param spec.
        if name == "params":
            return self.value

        return super().__getattribute__(name)

    def __str__(self):
        buffer = StringIO()
        self.write(buffer)
        return buffer.getvalue()

    def __eq__(self, other):
        return super().__eq__(other)

    @property
    def value(self):
        """Get a dictionary of block parameter values."""
        return MFParams.value.fget(self)

    @value.setter
    def value(self, value):
        """Set block parameter values from a dictionary."""

        if value is None or not any(value):
            return

        params = type(self).coerce(value.copy(), set_default=True)
        MFParams.value.fset(self, params)

    @classmethod
    def coerce(
        cls, params: Dict[str, Any], set_default: bool = False
    ) -> Dict[str, MFParam]:
        """
        Check that the dictionary contains only expected parameters,
        raising an error if any unrecognized parameters are provided.

        Dictionary values may be subclasses of `MFParam` or values
        provided directly. If the former, optionally set default
        values for any missing member parameters.
        """

        known = dict()
        for param_name, param_spec in cls.params.copy().items():
            param = params.pop(param_name, param_spec)
            spec_type = type(param_spec)
            real_type = type(param)
            if real_type is MFParamSpec:
                # implicitly support mapping of param specs
                pass
            if issubclass(real_type, MFParam):
                if param.value is None and set_default:
                    param.value = param_spec.default_value
            elif issubclass(spec_type, MFScalar) and real_type == spec_type.T:
                param = spec_type(value=param, **asdict(param_spec))
            else:
                raise TypeError(
                    f"Expected '{param_name}' as {spec_type}, got {real_type}"
                )

            known[param_name] = param

        if any(params):
            raise ValueError(f"Unrecognized parameters:\n{pformat(params)}")

        return known

    @classmethod
    def load(cls, f, **kwargs):
        """Load the block from file."""
        name = None
        index = None
        found = False
        params = dict()
        members = cls.params

        while True:
            pos = f.tell()
            line = f.readline()
            if line == "":
                raise ValueError("Early EOF, aborting")
            if line == "\n":
                continue
            words = strip(line).lower().split()
            key = words[0]
            if key == "begin":
                found = True
                name = words[1]
                if len(words) > 2 and str.isdigit(words[2]):
                    index = int(words[2])
            elif key == "end":
                break
            elif found:
                param = get_param(members, name, key)
                if param is None:
                    continue

                spec = asdict(param)
                kwrgs = {**kwargs, **spec}
                ptype = type(param)

                # set array cwd and shape from context
                if ptype is MFArray:
                    kwrgs["cwd"] = SimContext.get("cwd")
                    kwrgs["shape"] = (
                        param.shape
                        if isinstance(param.shape[0], int)
                        else tuple(
                            [SimContext.get(dim) for dim in param.shape]
                        )
                    )

                # set composite parameter members
                if ptype is MFRecord:
                    kwrgs["params"] = param.data.copy()
                if ptype is MFKeystring:
                    kwrgs["params"] = param.data.copy()

                # load the parameter
                f.seek(pos)
                params[param.name] = ptype.load(f, **kwrgs)

        return cls(name=name, index=index, params=params)

    def write(self, f):
        """Write the block to file."""
        index = self.index if self.index is not None else ""
        begin = f"BEGIN {self.name.upper()} {index}\n"
        end = f"END {self.name.upper()}\n"

        f.write(begin)
        super().write(f)
        f.write(end)


class MFBlocks(UserDict):
    """
    Mapping of block names to blocks. Acts like a
    dictionary, also supports named attribute access.
    """

    def __init__(self, blocks=None):
        MFBlocks.check(blocks)
        super().__init__(blocks)
        for key, block in self.items():
            setattr(self, key, block)

    def __repr__(self):
        return pformat(self.data)

    def __eq__(self, other):
        tother = type(other)
        if issubclass(tother, MFBlocks):
            other = other.value
        if issubclass(tother, Mapping):
            return OrderedDict(sorted(self.value)) == OrderedDict(
                sorted(other)
            )
        return False

    @staticmethod
    def check(items):
        """
        Raise if any items are not instances of `MFBlock` or subclasses.
        """
        if not items:
            return
        elif isinstance(items, dict):
            items = items.values()
        not_blocks = [
            b
            for b in items
            if b is not None and not issubclass(type(b), MFBlock)
        ]
        if any(not_blocks):
            raise TypeError(f"Expected MFBlock subclasses, got {not_blocks}")

    @property
    def value(self) -> Dict:
        """
        Get a nested dictionary of block values. This is a
        nested mapping of block names to blocks, where each
        block maps parameter names to parameter values.
        """
        return {k: v.value for k, v in self.items()}

    @value.setter
    def value(self, value: Optional[Dict]):
        """Set block values from a nested dictionary."""

        if not value:
            return

        blocks = value.copy()
        MFBlocks.check(blocks)
        self.update(blocks)
        for key, block in self.items():
            setattr(self, key, block)

    def write(self, f, **kwargs):
        """Write the blocks to file."""
        for block in self.values():
            block.write(f, **kwargs)
