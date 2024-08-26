"""NumPy utilities and `ndarray` wrapper classes."""

from typing import Sequence, Tuple

import numpy as np
from numpy.lib.mixins import NDArrayOperatorsMixin
from numpy.typing import ArrayLike


def is_constant(a: np.ndarray) -> bool:
    """Checks whether the given array is constant."""
    return np.ptp(a) == 0.0


def same_shape(arrays: Sequence[ArrayLike]):
    """Checks whether the arrays have the same shape."""
    shapes = [v.shape for v in arrays]
    return not np.ptp(shapes)


class ConstantArray(NDArrayOperatorsMixin):
    """
    Provides `np.ndarray` interoperability for constant arrays:
    an array-like that stores a single scalar instead of a full
    array and enforces an array's constancy upon initialization
    from a non-scalar.

    Notes
    -----

    One benefit is a smaller memory footprint for huge arrays.
    """

    def __init__(self, value: ArrayLike, shape: Tuple[int]):
        if np.isscalar(value):
            self._value = value
        else:
            if not is_constant(value):
                raise ValueError(
                    "Expected scalar or constant array, " f"got: {value}"
                )
            value = np.array(value).item(0)

        self._value = value
        self._shape = shape

    @property
    def shape(self) -> Tuple[int]:
        return self._shape

    def __array__(self, dtype=None, copy=None) -> np.ndarray:
        if copy:
            raise ValueError("Copy not supported")
        value = np.ones(self._shape)
        if dtype:
            value = value.astype(dtype)
        return value * self._value

    def __array_ufunc__(self, ufunc, method, *inputs, **kwargs):
        value = self.__array__()
        if len(inputs) == 1:
            result = value.__array_ufunc__(ufunc, method, value, **kwargs)
        else:
            result = value.__array_ufunc__(
                ufunc, method, value, *inputs[1:], kwargs
            )
        if not isinstance(result, np.ndarray):
            raise NotImplementedError(f"{str(ufunc)} has not been implemented")

        if result.shape != self.shape:
            raise ValueError(
                f"{str(ufunc)} result changed shape: "
                f"{self.shape} -> {result.shape}"
            )

        if not is_constant(result):
            raise ValueError(f"Result not constant: {result}")

        tmp = [None for _ in self.shape]
        self.__setitem__(slice(*tmp), result)
        return self


class LayeredArray(NDArrayOperatorsMixin):
    """
    Provides `np.ndarray` interoperability for layered arrays: an
    array-like class that provides easy access to grid layers and
    enforces shape constraints (e.g., layers' shapes must match).

    Notes
    -----

    The `nlay` property indicates the number of layers in the array.

    All layers must have the same shape; this is checked in `__init__`.

    Resources
    ---------
    - https://numpy.org/doc/stable/user/basics.interoperability.html
    - https://numpy.org/doc/stable/user/basics.ufuncs.html#ufuncs-basics

    """

    def __init__(self, layers: Sequence[ArrayLike]):
        if len(layers) == 0:
            raise ValueError("Must provide layer arrays")
        if not same_shape(layers):
            raise ValueError(f"Layer shapes don't match: {layers}")
        first = layers[0]
        if np.ndim(first) > 2:
            raise ValueError("Layers must be at most 2 dimensions")
        self._value = layers
        self._shape = first.shape

    def __array__(self, dtype=None, copy=None) -> np.ndarray:
        if dtype:
            return self._value.astype(dtype, copy or False)
        if copy:
            return np.copy(self._value)
        return np.reshape(self._value, self._shape)

    def __array_ufunc__(self, ufunc, method, *inputs, **kwargs):
        value = self.__array__()
        if len(inputs) == 1:
            result = value.__array_ufunc__(ufunc, method, value, **kwargs)
        else:
            result = value.__array_ufunc__(
                ufunc, method, value, *inputs[1:], kwargs
            )
        if not isinstance(result, np.ndarray):
            raise NotImplementedError(f"{str(ufunc)} has not been implemented")

        if not same_shape(result):
            raise ValueError(f"Layer shapes don't match: {result}")

        first = result[0]
        if first.shape != self.shape:
            raise ValueError(
                f"{str(ufunc)} result changed shape: "
                f"{self.shape} -> {first.shape}"
            )

        tmp = [None for _ in self.shape]
        self.__setitem__(slice(*tmp), result)
        return self

    @property
    def shape(self) -> Tuple[int]:
        return self._shape

    @property
    def nlay(self) -> int:
        return self.shape[0]

    def layer(self, k: int = 0) -> np.ndarray:
        """Return the given layer."""
        return self._value[k]


G
