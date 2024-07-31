import sys
from pathlib import Path
from typing import List

from flopy4.utils import get_member_classes

components = [p for p in Path(__file__).glob("*.py") if "_" not in p.stem]
__all__ = [p.stem for p in components]


def get_component_classes() -> List[type]:
    return get_member_classes(sys.modules[__name__])
