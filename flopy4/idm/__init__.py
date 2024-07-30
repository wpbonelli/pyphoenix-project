import sys
from typing import Iterator

from flopy4.utils import find_classes

__all__ = ["gwfdis", "gwfic"]


def find_components() -> Iterator[type]:
    return find_classes(sys.modules[__name__])
