from abc import ABC, abstractmethod

import numpy as np

from flopy4.constants import How


class MFArray(ABC):
    """
    MODFLOW 6 array representation.
    """

    @abstractmethod
    def __init__(self):
        self._flat = None
        self._how = None
        self._layered = None

    @property
    def values(self):
        """

        Returns
        -------

        """
        if self._layered:
            arr = []
            for mfa in self._flat:
                arr.append(mfa.values)
            return np.array(arr)

        if self._how == How.constant:
            return np.ones(self._shape) * self._flat * self.factor
        else:
            return self._flat.reshape(self._shape) * self.factor

    @property
    def raw_values(self):
        """

        Returns
        -------

        """
        if self._layered:
            arr = []
            for mfa in self._flat:
                arr.append(mfa.raw_values)
            return np.array(arr)

        if self._how == How.constant:
            return np.ones(self._shape) * self._flat
        else:
            return self._flat.reshape(self._shape)

    @property
    def factor(self):
        """

        Returns
        -------

        """
        if self._layered:
            factor = [mfa.factor for mfa in self._flat]
            return factor

        factor = self._factor
        if self._factor is None:
            factor = 1.
        return factor

    @property
    def how(self):
        """

        Returns
        -------

        """
        if self._layered:
            how = [mfa.how for mfa in self._flat]
            return how

        return self._how
