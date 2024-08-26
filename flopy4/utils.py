"""Miscellaneous utilities"""

from operator import add
from collections.abc import MutableMapping
from typing import Dict, Iterator


def depth(d):
    """
    Get the nesting depth of a dictionary.
    Referenced from https://stackoverflow.com/a/23499101/6514033.
    """
    if isinstance(d, dict):
        return 1 + (max(map(depth, d.values())) if d else 0)
    return 0


def find_upper(s: str):
    """Yield the uppercase characters in the string."""
    for i in range(len(s)):
        if s[i].isupper():
            yield i


_FLAG_FIRST = object()

def flatten(d, join=add, lift=lambda x:(x,), split=False) -> dict | Iterator[Dict]:
    """
    Flatten nested dictionaries in the given dictionary into
    a single dictionary with hierarchical keys.

    Adapted from https://stackoverflow.com/a/6043835/6514033.
    """
    results = []
    def visit(subdict, results, partialKey):
        for k,v in subdict.items():
            newKey = lift(k) if partialKey==_FLAG_FIRST else join(partialKey,lift(k))
            try:
                visit(v, results, newKey)
                if split:
                    yield v
            except:
                results.append((newKey, v))
    visit(d, results, _FLAG_FIRST)
    if not split:
        return dict(results)


def get_alias_map(cls) -> Dict[str, str]:
    """
    Get a map of field names to aliases
    for an `attrs`-based class.
    """
    return {a.name: a.alias for a in cls.__attrs_attrs__}
