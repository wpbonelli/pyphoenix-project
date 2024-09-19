from lark import Transformer

from flopy4.utils import str2bool


class DFNTransformer(Transformer):
    """
    Transforms a parse tree for the MODFLOW 6
    specification language into a nested dict
    suitable for generating an object model.

    Notes
    -----
    Rather than a flat list of parameters for each component,
    which a subsequent step is responsible for turning into a
    an object hierarchy, we derive the hierarchical parameter
    structure from the DFN file and return a dict of blocks,
    each of which is a dict of parameters. This happens in
    the `dfn()` method.

    Note also the `block()` and `name` methods, each returning
    a key/value tuple. These are for parameter block and name.
    These are only needed because we define nonterminals for
    block/name in order to delimit parameters; we don't want
    to assume the existence of newlines in between parameters
    (groups of attributes). These methods return such a tuple
    so they can be passed straight to `dict()` when parameter
    node methods are called.

    See https://lark-parser.readthedocs.io/en/stable/visitors.html#transformer
    for more info on how transformers work.
    """

    def key(self, k):
        """Attribute name"""
        (k,) = k
        return str(k).lower()

    def value(self, v):
        """Attribute value"""
        (v,) = v
        v = str(v).strip()
        if v.lower() in ["true", "false"]:
            return str2bool(v)
        if v.isdigit():
            return int(v)
        try:
            return float(v)
        except:
            return v

    def attribute(self, a):
        """Parameter attribute (not block or name)"""
        return str(a[0]), a[1]

    def name(self, n):
        """Parameter name"""
        (n,) = n
        return "name", str(n)

    def block(self, b):
        """Parameter block"""
        (b,) = b
        return "block", str(b)

    parameter = dict

    def dfn(self, d):
        """Full component"""
        _dfn = dict()
        for param in d:
            block = param.pop("block")
            name = param.pop("name")
            if block not in _dfn:
                _dfn[block] = dict()
            _dfn[block][name] = param
        return _dfn
