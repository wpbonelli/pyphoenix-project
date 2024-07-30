from abc import abstractmethod
from collections import OrderedDict, UserDict
from dataclasses import dataclass, fields
from io import StringIO
from pprint import pformat
from typing import Any, Dict, Mapping, Optional, Tuple

from flopy4.constants import MFReader


@dataclass
class MFParamSpec:
    """
    MF6 input parameter specification.
    """

    block: Optional[str] = None
    name: Optional[str] = None
    type: Optional[str] = None
    longname: Optional[str] = None
    description: Optional[str] = None
    deprecated: bool = False
    in_record: bool = False
    layered: bool = False
    optional: bool = True
    numeric_index: bool = False
    preserve_case: bool = False
    repeating: bool = False
    tagged: bool = True
    reader: MFReader = MFReader.urword
    shape: Optional[Tuple[str | int, ...]] = None
    default_value: Optional[Any] = None

    @classmethod
    def fields(cls):
        """
        Get the MF6 input parameter field specification.
        These uniquely describe the MF6 input parameter.

        Notes
        -----
        This is equivalent to `dataclasses.fields(MFParamSpec)`.
        """
        return fields(cls)

    @classmethod
    def load(cls, f) -> "MFParamSpec":
        """
        Load an MF6 input input parameter specification
        from a definition file.
        """
        # todo: also support toml?
        return cls._load_dfn(f)

    @classmethod
    def _load_dfn(cls, f):
        spec = dict()
        members = cls.fields()

        # find keyword fields
        keywords = [m.name for m in members if m.type == "keyword"]

        while True:
            line = f.readline()
            if not line or line == "\n":
                break
            words = line.strip().lower().split()
            key = words[0]
            val = " ".join(words[1:])
            if key in keywords:
                spec[key] = val == "true"
            elif key == "reader":
                spec[key] = MFReader.from_str(val)
            elif key == "shape":
                shape = tuple(val.replace("(", "").replace(")", "").split(","))
                try:
                    shape = tuple([int(dim) for dim in shape])
                except:
                    pass
                spec[key] = shape
            else:
                spec[key] = val

        return cls(**spec)

    def with_name(self, name) -> "MFParamSpec":
        """Set the parameter name and return the parameter."""
        self.name = name
        return self

    def with_block(self, block) -> "MFParamSpec":
        """Set the parameter block and return the parameter."""
        self.block = block
        return self


class MFParam(MFParamSpec):
    """
    MODFLOW 6 input parameter. Can be a scalar or compound of
    scalars, an array, or a list (i.e. a table).

    Notes
    -----
    This class plays a dual role: first, to define blocks that
    specify the input required for MF6 components; and second,
    as a data access layer by which higher components (blocks,
    packages, etc) can read/write parameters. The former is a
    developer task (though it may be automated as classes are
    generated from DFNs) while the latter happens at runtime,
    but both APIs are user-facing; the user can first inspect
    a package's specification via class attributes, then load
    an input file and inspect package data via instance attrs.

    Specification attributes are set at import time. A parent
    block or package defines parameters as class attributes,
    including a description, whether the parameter is optional,
    and other information specifying the parameter.

    The parameter's value is an instance attribute that is set
    at load time. The parameter's parent component introspects
    its constituent parameters then loads each parameter value
    from the input file. This is like "hydrating" a definition
    from a data store as in single-page web applications (e.g.
    React, Vue) or ORM frameworks (Django).
    """

    @abstractmethod
    def __init__(
        self,
        block=None,
        name=None,
        type=None,
        longname=None,
        description=None,
        deprecated=False,
        in_record=False,
        layered=False,
        optional=True,
        numeric_index=False,
        preserve_case=False,
        repeating=False,
        tagged=False,
        reader=MFReader.urword,
        shape=None,
        default_value=None,
    ):
        super().__init__(
            block=block,
            name=name,
            type=type,
            longname=longname,
            description=description,
            deprecated=deprecated,
            in_record=in_record,
            layered=layered,
            optional=optional,
            numeric_index=numeric_index,
            preserve_case=preserve_case,
            repeating=repeating,
            tagged=tagged,
            reader=reader,
            shape=shape,
            default_value=default_value,
        )

    def __str__(self):
        buffer = StringIO()
        self.write(buffer)
        return buffer.getvalue()

    def __eq__(self, other):
        if isinstance(other, MFParam):
            return self.value == other.value
        try:
            return self.value == other
        except:
            return False

    @property
    @abstractmethod
    def value(self) -> Optional[Any]:
        """Get the parameter's value."""
        pass

    @abstractmethod
    def write(self, f, **kwargs):
        """Write the parameter to file."""
        pass


class MFParams(UserDict):
    """
    Mapping of parameter names to parameters. Acts like
    a dictionary, also supports named attribute access.
    """

    def __init__(self, params=None):
        MFParams.check(params)
        super().__init__(params)
        for key, param in self.items():
            setattr(self, key, param)

    def __repr__(self):
        return pformat(self.data)

    def __eq__(self, other):
        tother = type(other)
        if issubclass(tother, MFParams):
            other = other.value
        if issubclass(tother, Mapping):
            return OrderedDict(sorted(self.value)) == OrderedDict(
                sorted(other)
            )
        return False

    @staticmethod
    def check(items):
        """
        Raise if any items are not instances of `MFParam` or subclasses.
        """
        if not items:
            return
        elif isinstance(items, dict):
            items = items.values()
        not_params = [
            p
            for p in items
            if p is not None and not issubclass(type(p), MFParam)
        ]
        if any(not_params):
            raise TypeError(f"Expected MFParam subclasses, got {not_params}")

    @property
    def value(self) -> Dict[str, Any]:
        """Get a dictionary of parameter values."""
        return {k: v.value for k, v in self.items()}

    @value.setter
    def value(self, value: Optional[Dict[str, Any]]):
        """Set parameter values from a dictionary."""

        if value is None or not any(value):
            return

        params = value.copy()
        MFParams.check(params)
        self.update(params)
        for key, param in self.items():
            setattr(self, key, param)

    def write(self, f, **kwargs):
        """Write the parameters to file."""
        for param in self.values():
            param.write(f, **kwargs)
