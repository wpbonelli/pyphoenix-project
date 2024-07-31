from collections import defaultdict
from inspect import getmembers, isclass
from typing import List


def get_member_classes(module) -> List[type]:
    """Find classes in the given module."""
    return [m for _, m in getmembers(module) if isclass(m)]


def uppers(s: str) -> str:
    """Get the uppercase characters in the given string."""
    return "".join([c for c in s if c.isupper()])


def strip(s: str) -> str:
    """
    Remove comments from and replace commas in the given string.

    Parameters
    ----------
    s: str
        the string


    Returns
    -------
        str : line with comments removed and commas replaced
    """

    for comment_flag in ["//", "#", "!"]:
        s = s.split(comment_flag)[0]
    s = s.strip()
    return s.replace(",", " ")


class attrdict(defaultdict):
    def __getattr__(self, key):
        return self[key]

    def __setattr__(self, key, val):
        self[key] = val


def tree():
    """
    An autovivifying dictionary. That is, a dictionary
    with arbitrary nesting with no need to create each
    child explicitly. Named attribute access works too.

    Notes
    -----
    See https://gist.github.com/hrldcpr/2012250.

    Examples
    --------
    users = tree()
    users['x']['y'] = 'z'

    """
    return attrdict(tree)
