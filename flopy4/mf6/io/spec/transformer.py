from itertools import filterfalse
from typing import Dict, Iterable, Iterator, List, Union

from lark import Token, Transformer

from flopy4.io.lark import parse_string

TYPE_REPRESENTATIONS = {"recarray": List, "record": Dict, "keystring": Union}
"""
Intermediate representations of composite parameter
types, suitable for generating an object model from.
"""


def expand_composites(params: Iterable[dict], last=None) -> Iterator[dict]:
    """Recursively expand composite parameters into nested dictionaries."""

    params = iter(params)
    while param := next(params, None):
        if param is None:
            break

        split = param["type"].split()
        ptype = split[0]
        _last = split[-1]

        if ptype in ["recarray", "keystring", "record"]:
            if ptype == _last:
                raise ValueError(
                    f"Composite parameter has no components: {param}"
                )
            yield {
                **param,
                **{
                    "components": {
                        c["name"]: c
                        for c in expand_composites(params, last=_last)
                    },
                },
            }
        else:
            yield param

        if param["name"] == last:
            return


class DFNTransformer(Transformer):
    """
    Transforms a parse tree for the MODFLOW 6
    specification language into a nested AST
    suitable for generating an object model.

    Notes
    -----

    This happens in two phases. First the transformer visits
    each node in the tree from the bottom up (depth first),
    and produces a dict of blocks, each of which is a flat
    list of variables as appears in definition files. These
    do not correspond directly to input parameters, since a
    parameter might be defined by multiple variables; e.g.,
    a list (recarray), record, or union (keystring).

    A subsequent step inspects variable attributes to infer
    composite parameters (`in_record` etc) and expands them
    into nested dictionaries with an extra entry "composite"
    whose value is "list", "record", or "union". Parameters
    which are not composites (i.e., leaves on the parameter
    tree) do not have this entry. This allows generating an
    object model where components and composite parameters
    are represented as `attrs`-based classes and leaves are
    attributes.

    Specifically, TODO
    """

    def key(self, k):
        (k,) = k
        return str(k).lower()

    def value(self, v):
        (v,) = v
        return str(v)

    def attribute(self, p):
        return str(p[0]), str(p[1])

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

    def block(self, _block):
        # filter out comment/formatting characters, which
        # haven't been transformed and are still `Token`s.
        _block = list(filterfalse(lambda p: isinstance(p, Token), _block))
        # items 1 and 2 are component and subcomponent name,
        # item 3 is the block's name, subsequent items are
        # the block's variables.
        name = _block[2][1]
        params = _block[3:]
        # infer composite parameters from block variables
        # and expand them into nested dictionaries.
        params = expand_composites(params)
        params = {p["name"]: p for p in params}
        return name, params

    string = parse_string
    dfn = dict
