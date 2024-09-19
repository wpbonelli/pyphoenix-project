__all__ = ["make_parser", "DFNTransformer"]

from flopy4.mf6.io.spec.parser import make_parser
from flopy4.mf6.io.spec.transformer import DFNTransformer

_parser = make_parser()
_transformer = DFNTransformer()


def load(f) -> dict:
    """
    Deserialize a file-like object containing a MODFLOW 6
    input component definition to a dictionary.
    """
    tree = _parser.parse(f.read())
    return _transformer.transform(tree)


def dump(d: dict):
    # TODO
    pass
