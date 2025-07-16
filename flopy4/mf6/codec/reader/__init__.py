from os import PathLike
from pathlib import Path
from typing import Any

from flopy4.mf6.codec.reader.parser import make_component_parser, make_generic_parser
from flopy4.mf6.codec.reader.transformer import ComponentTransformer, GenericTransformer


def load(path: str | PathLike, component_name: str | None = None) -> Any:
    """
    Load and parse an MF6 input file.

    Parameters
    ----------
    path : str | PathLike
        Path to the MF6 input file
    component : Optional[str]
        Component name for specialized parsing (e.g., 'chd')

    Returns
    -------
    Any
        Parsed MF6 input file structure
    """
    path = Path(path)
    with open(path, "r") as f:
        data = f.read()
    return loads(data, component_name=component_name)


def loads(data: str, component_name: str | None = None) -> Any:
    """
    Parse MF6 input file content from string.

    Parameters
    ----------
    data : str
        MF6 input file content as string
    component : Optional[str]
        Component name for type-aware parsing (e.g., 'chd')

    Returns
    -------
    Any
        Parsed MF6 input file structure
    """

    if component_name is None:
        parser = make_generic_parser()
        transformer = GenericTransformer()
    else:
        parser = make_component_parser(component_name)
        transformer = ComponentTransformer(component_name)
    return transformer.transform(parser.parse(data))
