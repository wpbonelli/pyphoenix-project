from collections.abc import MutableMapping
from keyword import kwlist
from typing import Any, Iterator, Optional, TypeVar
from warnings import warn

from attrs import asdict

from flopy4.utils import get_alias_map

T = TypeVar("T")


class MapAttrs[T](MutableMapping[str, T]):
    """
    Mixin for `attrs` classes that provides dictionary-like behavior &
    tries to set up "public" named attributes for "private" arguments.

    Notes
    -----

    This mixin is motivated by the fact that private-ish attributes (i.e.,
    attributes named with a single leading underscore) are convenient and
    popular, and can also help solve field name collisions with reserved
    Python keywords.

    Named attributes cannot conflict with a Python keyword:

    >>> class X:
    >>>     continue = ...
    SyntaxError: invalid syntax

    But sometimes we want to name a field something like `continue`. One
    approach is to call it `_continue` instead, but this is awkward for
    initializer arguments, and is a bit painful in general; ideally we
    want attributes that can take any names.

    `attrs`, recognizing this, removes a leading underscore from `__init__`
    method parameters, and registers this as an `alias` in the `Attribute`
    specification. But that's all it does.

    From the `attrs` docs[0]:

    > `attrs` follows the doctrine that there is no such thing as a private
    argument and strips the underscores from the name when writing the __init__
    method signature.
    (https://www.attrs.org/en/stable/init.html#private-attributes-and-aliases)

    This mixin tries to do the same thing for named attribute accessors. If
    an attribute's name does not collide with a reserved keyword, the class
    is given a property whose name has the leading underscore stripped off.

    If the name collides with a keyword, dictionary access is convenient;
    `MutableMapping` is implemented such that the class can be access and
    manipulated as a dictionary.

    Note: child classes *must* be decorated with `attrs.define()`. This is not
    optional, nothing will work without it!

    """

    def __new__(cls, clsname, bases, attrs) -> None:
        if clsname != "MapAttrs":
            # setup alias map
            cls.__attrs_aliases__ = get_alias_map(cls)

            # try aliased properties setup. warn if
            # names collide with reserved keywords!
            for name, alias in cls.__attrs_aliases__.items():
                if alias in kwlist:
                    warn(f"{cls} field name is a reserved keyword: {name}")
                else:
                    attrs[name] = property(lambda s: s[alias])

        return super().__new__(cls, clsname, bases, attrs)

    def __getitem__(self, key: str) -> T:
        return asdict(self).get(self._aliases[key])

    def __setitem__(self, key: str, value: T) -> None:
        setattr(self, self._aliases[key], value)

    def __delitem__(self, key: str) -> None:
        setattr(self, self._aliases[key], None)

    def __iter__(self) -> Iterator[str]:
        return iter(asdict(self))

    def __len__(self) -> int:
        return len(asdict(self))

    def get(self, key: str, default: Optional[Any] = None) -> Any:
        """
        Find a field matching the given key (name).
        """
        cls = type(self)
        names = [a.name for a in cls.__attrs_attrs__]
        aliases = getattr(
            cls, "__attrs_aliases__", get_alias_map(cls)
        ).values()
        if key in names or key in aliases:
            return getattr(self, key)
        if default is not None:
            return default
        raise KeyError(f"Attribute not found: {key}")
