from abc import (
    abstractmethod,
    ABCMeta
)


class MFParameter(metaclass=ABCMeta):
    """
    MODFLOW 6 input parameter. Can be a
    scalar, array, or list. Parameters
    are constituents of input blocks.
    """

    @abstractmethod  # https://stackoverflow.com/a/44800925/6514033
    def __init__(self, name=None, description=None, optional=False):
        # private
        self._name = name
        self._value = None

        # public
        self.description = description
        self.optional = optional

    @property
    def name(self):
        """Get the parameter's name."""
        return self._name

    @property
    @abstractmethod
    def value(self):
        """Get the parameter's value."""
        pass

    @property
    def metadata(self):
        # todo: factor out parameter metadata class?
        return {
            "name": self.name,
            "description": self.description,
            "optional": self.optional,
        }
