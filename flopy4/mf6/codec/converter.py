from typing import Any

import xattree

from flopy4.mf6.component import Component


def unstructure_component(value: Component) -> dict[str, Any]:
    """Simple converter: component -> dict with validation."""
    return xattree.asdict(value)


def structure_component(cls: type[Component], data: dict[str, Any]) -> Component:
    """Simple converter: dict -> component with validation."""
    return xattree.structure(data, cls)
