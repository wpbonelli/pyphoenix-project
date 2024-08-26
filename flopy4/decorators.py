"""
A few function and class decorators, mainly for
`attrs`-based classes. Some unlock goodies for
framework foundation classes and fall back to
a default implementation for other types.
"""

from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from cattrs import Converter
from numpy.typing import ArrayLike
from typing_extensions import Protocol


class Update(Protocol):
    """
    Update a field on an `attrs`-based class based on
    another field.
    """

    def __call__(self, obj, value, **kwargs) -> Any: ...


def depend(cls, attr_name, update: Optional[Update]):
    """
    Decorator for `attrs`-based classes expressing an
    upstream field dependency.

    Notes
    -----

    Decorate an `attrs` class to indicate that one of
    its fields depends on another field. This implies
    any change in the former should be propagated to
    the latter via the `update` callback, which gets
    the instance of the decorated class and value of
    the field as arguments when the upstream changes.

    The update callback is applied on initialization
    and further writes. This is done by intercepting
    and modifying `__init__` and `__setattr__` calls.

    The class *must* be `attrs`-based. It *may* be a
    subclass of `Context` for extra goodies.

    If the decorated class inherits from `Context`,
    the dependent field need not be in the class;
    signals are broadcast to the full context tree.
    Otherwise the field needs to be in the class.

    """

    old_init = cls.__init__
    old_setattr = cls.__setattr__

    def _maybe_callback(self, value):
        if update:
            # TODO: try/except with custom exception type
            # (FailedUpdate?)
            value = update(self, value)
        return value

    def _setattr(self, name: str, value):
        if value is not None:
            value = _maybe_callback(self, value)
        old_setattr(self, name, value)

    def _init(self, *args, **kwargs):
        value = kwargs.pop(attr_name, None)
        if value is not None:
            kwargs[attr_name] = _maybe_callback(self, value)
        old_init(self, *args, **kwargs)

    cls.__init__ = _init
    cls.__setattr__ = _setattr
    return cls


class ConstraintViolation(Exception):
    """Failed constraint."""

    pass


class Constraint(Protocol):
    """
    Constrain something about a field value on an `attrs`-based class.
    """

    def __call__(self, obj, value, **kwargs) -> bool: ...


def constrain(
    cls,
    attr_name: str,
    fail_msg: str | Callable[[Any, Any], str],
    constraint: Constraint,
):
    """
    Decorator to apply a constraint to a field on an
    `attrs`-based class.

    Notes
    -----

    The constraint is applied on initialization and
    subsequent writes. This is done by intercepting
    and modifying `__init__` and `__setattr__` calls.

    The class *must* be `attrs`-based.
    """

    def _update(self, value) -> None:
        if not constraint(self, value):
            msg = (
                fail_msg(self, value)
                if isinstance(fail_msg, Callable)
                else fail_msg
            )
            raise ConstraintViolation(msg)
        return value

    return depend(cls, attr_name, _update)


def shape(cls, attr_name: str, shp: Tuple[int]):
    """
    Decorator to constrain the shape of an array-like field
    on an `attrs`-based class.

    Notes
    -----

    The class *must* be `attrs`-based.
    """

    def _check_shape(_, arr: ArrayLike) -> bool:
        return arr.shape == shp

    return constrain(
        cls,
        attr_name,
        lambda arr: (
            "Wrong array shape, " f"expected {shp}, " f"got {arr.shape}"
        ),
        _check_shape,
    )


def paired_file(cls, attr_name: str):
    """
    Decorator to bind instances of a class to a file.

    Notes
    -----

    An attribute to hold the file `Path` is added to the
    class, and a parameter to `__init__`; both are named
    `attr_name`.

    The class need not be `attrs`-based.
    """
    old_init = cls.__init__

    def _init(self, *args, **kwargs):
        old_init(self, *args, **kwargs)
        path = kwargs.pop(attr_name, None)
        if path:
            path = Path(path).expanduser()
            if not path.is_file():
                raise ValueError(f"Path is not a file: {path}")
        setattr(self, attr_name, path)

    cls.__init__ = _init
    return cls


def paired_dir(cls, attr_name: str):
    """
    Decorator to bind instances of a class to a directory.

    Notes
    -----

    An attribute to hold the directory `Path` is added
    to the class, and a parameter to `__init__`; both
    are named `attr_name`.

    The class need not be `attrs`-based.
    """
    old_init = cls.__init__

    def _init(self, *args, **kwargs):
        old_init(self, *args, **kwargs)
        path = kwargs.pop(attr_name, None)
        if path:
            path = Path(path).expanduser()
            if not path.is_dir():
                raise ValueError(f"Path is not a directory: {path}")
        setattr(self, attr_name, path)

    cls.__init__ = _init
    return cls


def io(cls, converters: Dict[str, Converter], default: str):
    """
    Class decorator to add `load` and `write` methods to a
    decorated class implementing `MapAttrs`.

    TODO: reimplement this as global configurable registry
    for IO formats instead of mixin/inheritance; mapping of
    subclasses to formats? use astropy.io as a reference

    Notes
    -----

    The component may have a one-to-many relationship with
    other files representing its subcomponents (e.g. model
    input files may reference package input files). This
    mixin first de/serializes the class it is applied to,
    then calls `load()` or `write()` on its subcomponents.

    This mixin assumes the class to which it is applied
    implements `Context`, enabling component discovery.
    """

    @classmethod
    def load(cls, f, format=default):
        obj = converters[format].loads(f.read())
        for name, child in obj.items():
            if hasattr(type(child), "load") and hasattr(child, "path"):
                setattr(obj, name, type(child).load(child.path))
        return cls(**obj)

    def write(self, f, format=default):
        f.write(converters[format].dumps(self))
        for child in self.values():
            if hasattr(child, "write") and hasattr(child, "path"):
                child.write(child.path)

    cls.load = classmethod(load)
    cls.write = write

    return cls
