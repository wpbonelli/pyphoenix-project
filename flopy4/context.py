"""Hierarchical context. Basic building block for program interfaces."""

from collections import ChainMap
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple
from functools import partial

from attrs import Attribute
from numpy.typing import ArrayLike
from treelib import Tree

from flopy4.decorators import shape as shape_base
from flopy4.map import MapAttrs
from flopy4.param import Param
from flopy4.utils import flatten as flatten_dict

Field = Param | List[Param] | MapAttrs[Param | List[Param]]
"""A type that can appear in a `Context`."""


class Context(MapAttrs[Field]):
    """
    An `attrs`-based collection of parameters, lists of parameters, and/or
    nested subcomponents. This is a general-purpose container for elements
    of a simulation which can be grouped into a hierarchy including parent
    (upwards) and child (downwards) references.

    Notes
    -----

    `Context` is a dict-like `attrs` class, whose attributes
    are of some type `Field`, which can be a `Parameter`, a
    list of parameters, or a mapping of parameters or lists
    of such. `Context` uses `MapAttrs` to act like a mapping.

    `Context` can have a name, where `MapAttrs` is anonymous.

    `Context` does a few more useful things:

        1. sets parent/child references on initialization
        2. sets parameter and subcomponent specification attributes
        3. defines a hierarchical/delimited `address` property
        4. provides a `find(name)` method which searches up and
        down the context tree for a field of the given name, in
        the following order within each component: self, parent,
        then children, with parents searching their own children.
        5. TODO: implement condensed repr for nested contexts

    **Specification**

    Class attributes `parameters` and `components` are attached to all child
    classes. These are maps of `attrs.Attribute` keyed by alias and contain
    the parameter and subcomponent specification, respectively. These allow
    the caller to ask the component about its members.

    Subclasses are expected to name their attributes publicly (no prefix),
    or with a leading underscore for "private"(-ish) attributes (See the
    `MapAttrs` docs for details).

    Note: children must use `@field()` for parameter/component attributes,
    and must be decorated with `@define`. Nothing will work without this!

    **Parents and children**

    `Context.__init__` accepts a `parent` and `children`, which allow
    situating the context in a nested hierarchy or making it the root
    of its own tree.

    `children` unsurprising as components typically keep pointers to
    their subcomponents.

    `parent` allows climbing nested contexts up to the root of the
    tree. If a component stands alone, its `parent` is `None`.

    TODO: use weak refs for parents to prevent memory leaks if/when a
    component's parent is removed?

    **Hierarchical addressing**

    Hierarchical addressing is useful for uniquely identifying the
    position of a context (or one of its parameters or components)
    in a nested hierarchy. Prefix resolution works by the mechanism
    described above.


    """

    def __new__(cls, clsname, bases, attrs) -> None:
        if clsname != "Component":
            attrs["spec"] = get_spec(cls)
        return super().__new__(cls, clsname, bases, attrs)

    def __init__(
        self,
        name: Optional[str] = None,
        parent: Optional["Context"] = None,
        separator: str = "/"
    ) -> None:
        # set attributes
        self.name = name
        self.parent = parent
        self.separator = separator

        # setup signals mechanism: just a registry of
        # listeners, each of which has a unique identifier.
        # this allows filtering callbacks for a given signal.
        self.listeners: Dict[str, Callable] = []

    def __attrs_post_init__(self):
        # self and parent listen to each other
        if self.parent:
            self.listen(self.parent.prefix, lambda n, v: self.notify(n, v))
            self.parent.listen(
                self.prefix, lambda n, v: self.parent.notify(n, v)
            )

        # set child contexts' parent pointers
        # and set up bidirectional listening
        # between self and children also
        for name, child in self.items():
            if isinstance(child, Context):
                child.parent = self
                setattr(self, name, child)
                self.listen(child.prefix, lambda n, v: self.notify(n, v))
                child.listen(self.prefix, lambda n, v: child.notify(n, v))

    @property
    def children(self) -> Dict[str, "Context"]:
        return {k: v for k, v in self.items() if isinstance(v, Context)}

    @property
    def context(self) -> Dict[str, Param]:
        return resolve(self, separator=self.separator)

    @property
    def prefix(self) -> str:
        if self.parent:
            return (
                f"{self.parent.prefix}"
                f"{self.separator}"
                f"{self.name}"
            )
        return self.name

    # Signaling mechanism

    def listen(self, name: str, callback: Callable):
        self.listeners[name] = callback

    def notify(self, name: str, value: Any):
        """
        Broadcast the parameter value to all listeners
        with a matching dependency. Overrides a method
        of the same name on `signal`-decorated classes.
        """
        for depends, callback in self.listeners:
            if name in depends:
                callback(value)

def get_spec(cls: type[Context]) -> Dict[str, Attribute]:
    spec: Dict[str, Attribute] = dict()
    spec.__doc__ = "Parameter and subcomponent specification"
    for attr in cls.__attrs_attrs__:
        if attr.type in [Param, List[Param]]:
            spec[attr.alias] = attr
        if issubclass(attr.type, Context):
            spec[attr.alias] = get_spec(attr.type)
    return spec

def resolve(context: Context, separator="/", merge=False) -> Dict[str, Any]:
    """
    Resolve the context and its parent context into a single
    dictionary with hierarchical keys delimited by the given
    `separator`. If `merge` is `True`, context items sharing
    the same name are merged and the prefix is stripped from
    keys, for a consolidated lookup table, where the current
    context takes precedence over its parent and so on.
    
    """
    flatten = partial(flatten_dict,
        d=context,
        join=lambda a,b: a+separator+b,
        lift=repr
    )
    if merge:
        maps = [{k.rpartition("/")[2]: v for k, v in m} for m in list(flatten(split=True))]
        return ChainMap(maps)
    return flatten()

def shape(cls, attr_name: str, shp: Tuple[int | str]):
    """
    Decorator to constrain the shape of an array-like field
    on a `Component` subclass explicitly or by reference to
    another field in the component context.

    Notes
    -----

    The class *must* inherit from `Component`. Nothing will
    work otherwise!

    """

    def _check_shape(component: Context, arr: ArrayLike) -> bool:
        def resolve_dims(shape: Tuple[int | str]) -> Iterator[int]:
            for dim in shape:
                if isinstance(dim, int):
                    yield dim
                msg = f"Couldn't find shape field: {dim}"
                dim = component.get(dim)
                if dim is None:
                    raise ValueError(msg)
                yield dim

        return arr.shape == tuple(resolve_dims(shp))

    return shape_base(
        cls,
        attr_name,
        lambda arr: (
            "Wrong array shape, " f"expected {shp}, " f"got {arr.shape}"
        ),
        _check_shape,
    )
