"""
This module implements the observer pattern for a
MODFLOW 6 component (simulation, model or package)
such that attributes of a parameter spec can refer
to the value of another parameter. E.g. an array's
shape is a tuple of grid dimensions, each of which
is a reference to another parameter (e.g. nrow and
ncol) in the same component or in a (grand-)parent.

This is useful for two purposes:

1) Updating parameters

Parameters whose specification depends on another
parameter need to know when the parameter's value
changes. E.g. arrays need to be cleared after the
grid's dimensions change, as the previous values
are no longer meaningful for the new model grid.

2) Loading parameters

The same mechanism can be used at load time to let
a dependent parameter resolve elements of its spec
when they become available. Assuming components of
the simulation are loaded in the proper order this
removes the need for a parameter to look up values
of unknown attributes at load time within a global
context; it will have already received a callback,
initializing the attribute when the unknown value
was resolved by another parameter's load routine.

Notes
-----

There are three relevant actors in the signaling
framework. These are: signal contexts, any class
which uses the `SignalContext` mixin; signalers,
which dispatch values; and listeners, which may
use signalers' values to resolve their own, and
are updated whenever the signaled value changes.

Signal contexts are assumed to be MF6 components
which consist of parameters and other components.

This way each package, model, and simulation acts
as a signaling context, within which a parameter
may register itself is a dependant or dependency.

Dependencies are registered by name such that any
dependant may select a subset of dependencies for
its own use. These are well-known at import time,
as they are drawn directly from the specification.

When the MF6 component inspects its parameters at
import time, it will detect and register internal
relationships. At load time it will then register
itself as a listener and a signaler on the parent
component's context, if one is passed as `context`
to `load()`. A package within a model context, or
a model or package in a simulation context, makes
a weak reference in both directions, which allows
broadcasts to the entire tree. This in turn means
parameters may depend on any other parameter. If
components are detached from their contexts, and
the context or component later disappears, links
do not keep the object alive (memory leak); weak
linking gaurantees immediate garbage collection.

As such parameter dependencies can operate in the
background and there is no need to maintain 2-way
references explicitly. Each component can concern
itself with its members and can assume it will be
be delivered any info it needs before it needs it
(moreover that it will always be kept up to date)
without explicit reference to any parent context.
The bookkeeping is done by the signals machinery.


TODO: Build a DAG of dependencies at load time and
use it to order components so dependent params get
their values before their own load time arrives.

TODO: Use weak references for subscriptions?
- https://docs.python.org/3/library/weakref.html

TODO: support context manager use
"""


# this may not work yet.. just got the vision down

from typing import Any, Callable, Optional


def signal(cls):
    """
    Class decorator expressing fulfillment of a parameter
    dependency. Classes which `@signal` broadcast a value
    to classes which `@depend` on them, when the value is
    first loaded or changed thereafter.

    To support the signaling protocol, a class must have
    a `value` property with a getter and setter. Signals
    work by intercepting calls to the setter and sending
    the value to any listeners via registered callbacks.
    """

    if not hasattr(cls, "value"):
        raise TypeError("Signal needs a 'value' property")

    cls.is_signal = True
    cls.callbacks = list()

    def listen(self, callback: Callable):
        """Register a listener callback."""
        # todo use weak reference
        self.callbacks.append(callback)

    def notify(self, name: str, value: Any):
        """Broadcast a value to all listeners."""
        for depends, callback in self.listeners:
            if name in depends:
                callback(value)

    def fset_value(self, value):
        self.notify(value)
        cls.value.fset(self, value)

    cls.listen = listen
    cls.notify = notify
    cls.value.fset = fset_value

    return cls


def depend(cls, *attrs):
    """
    Class decorator expressing a parameter dependency.
    Decorate component classes to indicate that one of
    its attributes requires another parameter's value.
    """

    def _callback(self, attr, value):
        """
        Callback function to set an attribute
        value and clear the component's value.
        """
        setattr(self, attr, value)
        self.value = None

    # override the class initializer,
    # register dependancy callbacks
    # with the signaling mechanism
    orig_init = cls.__init__

    def __init__(self, callback: Optional[Callable], *args, **kwargs):
        context = kwargs.get("context", None)
        depends = kwargs.get("depends", attrs)
        self.depends = list(set(depends))
        for attr in self.depends:
            # attribute must pre-exist
            if not hasattr(cls, attr):
                raise ValueError(f"{cls} has no attribute: {attr}")

            # register the callback
            callback = callback or _callback
            context.listen(
                lambda value: callback(self, attr, value),
            )
        orig_init(self, *args, **kwargs)

    cls.__init__ = __init__

    return cls


@signal
@depend
class SignalContext:
    """
    This class is intended to be mixed in with the
    `MFSimulation`, `MFModel` or `MFPackage` class
    such that MF6 component parameters may express
    dependencies upon other parameters in the same
    component or in a parent component.

    Subclasses should `listen()
    """

    def __enter__(self):
        # todo
        pass

    def __exit__(self, *exc):
        # todo
        pass

    def __setattr__(self, name, value):
        # hijack the behavior of `setattr`, since
        # that's the default `depend` callback...
        # if the context has any dependencies and
        # this is one of them, send the value out
        # to all registered listeners.
        if not hasattr(self, "depends"):
            super().__setattr__(name, value)
        if name in self.depends:
            self.notify(name, value)

    def notify(self, name: str, value: Any):
        """
        Broadcast the parameter value to all listeners
        with a matching dependency. Overrides a method
        of the same name on `signal`-decorated classes.
        """
        for depends, callback in self.listeners:
            if name in depends:
                callback(value)
