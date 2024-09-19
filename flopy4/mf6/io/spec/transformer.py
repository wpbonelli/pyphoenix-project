from itertools import dropwhile

from lark import Transformer

from flopy4.io.lark import parse_string
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
    each of which is a dict of parameters.

    See https://lark-parser.readthedocs.io/en/stable/visitors.html#transformer
    for more info on how transformers work.
    """

    def key(self, k):
        (k,) = k
        return str(k).lower()

    def value(self, v):
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

    def attribute(self, p):
        return str(p[0]), p[1]

    def parameter(self, p):
        return dict(p[1:])

    def paramname(self, n):
        (n,) = n
        return "name", str(n)

    def paramblock(self, b):
        (b,) = b
        return "block", str(b)

    def component(self, c):
        (c,) = c
        return "component", str(c)

    def subcompnt(self, s):
        (s,) = s
        return "subcomponent", str(s)

    def blockname(self, b):
        (b,) = b
        return "block", str(b)

    def block(self, b):
        b_ = dropwhile(lambda x: not isinstance(x, dict), b)
        params = {p["name"]: p for p in b_}
        return b[4][1], params

    string = parse_string
    dfn = dict
