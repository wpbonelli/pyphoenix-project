"""
Note: totally untested, just sketching the idea.

This module implements the observer pattern such
that an attribute of a parameter spec can refer
to the value of another parameter; e.g. array
shape as a tuple of grid dimensions.

Parameters whose specification depends on another
parameter need to know when the parameter's value
changes; e.g. arrays need to be cleared after the
grid's dimensions change (the previous values are
no longer meaningful or valid).

The same mechanism can be used at load time to let
a dependent parameter resolve elements of its spec
when they become available. Assuming components of
the simulation are loaded in the proper order this
removes the need for a global context mechanism. A
global view can be obtained from the simulation on
demand from its member components, whose hierarchy
is the single source of truth regarding simulation
settings and data, but this is unnecessary at load
time as we can now assume an array knows its shape
before it is loaded. Some kind of simulation-scope
context is needed to manage signaling but the load
mechanism wouldn't need to use it.
"""

from flopy4.param import MFParam, MFParamSpec

# temporary hack, todo: pull into simulation?
signalers = dict()
listeners = []


def listen(listener: MFParam, callback, *params):
    """
    Register a parameter to receive the values of the
    referenced parameters when they become available.
    Upon receipt of a value, the given callback runs.
    """

    # make sure the listener depends on the params
    depends = getattr(listener, "depends", False)
    if not depends:
        raise TypeError("Receiver has no dependencies")
    assert depends == list(set(params))

    # register the listener and callback
    listeners.append((tuple(depends), callback))


def tender(name, value):
    """Broadcast the parameter's value to all listeners."""
    for depends, callback in listeners:
        if name in depends:
            callback(value)


def signal(cls):
    """
    Class decorator expressing fulfillment of a parameter
    dependency. An `MFParam` subclass marked to `@signal`
    will broadcast its value to other `MFParam` instances
    whose attributes `@depend` on it.
    """

    if not issubclass(cls, MFParam):
        raise TypeError("Signals only support MFParams")

    cls.signals = True

    def fset(self, value):
        tender(value)
        cls.value.fset(self, value)

    cls.value.fset = fset

    orig_init = cls.__init__

    def __init__(self, *args, **kwargs):
        signalers[self.name] = self
        orig_init(self, *args, **kwargs)

    cls.__init__ = __init__
    return cls


def depend(cls, *fields):
    """
    Class decorator expressing a parameter dependency.
    Decorate `MFParam` subclasses to indicate that one
    or more fields require another parameter's value.
    """

    if not issubclass(cls, MFParam):
        raise TypeError("Signals only support MFParams")

    # mark the class' dependent fields
    cls.depends = list(set(fields))

    def callback(self, field, value):
        """
        Callback function, sets an attribute
        value and clears the parameter value.
        """
        setattr(self, field, value)
        self.value = None

    # override class initializer and
    # register the dependent fields
    # with the signaling mechanism
    orig_init = cls.__init__

    def __init__(self, *args, **kwargs):
        known = list(MFParamSpec.fields().keys())
        for field in fields:
            if field not in known:
                raise ValueError(f"Unknown field: {field}")
            listen(
                self,
                lambda value: callback(self, field, value),
                *getattr(self, field),
            )
        orig_init(self, *args, **kwargs)

    cls.__init__ = __init__

    return cls
