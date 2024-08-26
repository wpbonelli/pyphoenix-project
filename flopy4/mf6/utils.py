from typing import Any, Tuple


def parse_shape(shp: Any) -> Tuple[int | str]:
    """
    Parse a string representing an array shape into a tuple of `str` or `int.
    If `shp` is already a tuple of `str` or `int`, just return it unmodified.
    """
    if isinstance(shp, str):
        return tuple(
            [
                int(s.strip())
                for s in shp.replace("(", "").replace(")", "").split(",")
            ]
        )
    elif isinstance(shp, Tuple[int | str]):
        return tuple([int(s) for s in shp])
    else:
        raise ValueError(
            "Unsupported shape format, "
            "expected string `'(dim1, ...)'`, "
            "tuple of strings `('dim1', ...)`, "
            "or tuple of ints `(3, ...)`"
        )
