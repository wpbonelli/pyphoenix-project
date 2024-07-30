from inspect import getmembers, isclass
from typing import Iterator


def find_classes(module) -> Iterator[type]:
    """Find classes in given module."""
    for _, obj in getmembers(module):
        if isclass(obj):
            yield obj


def find_upper(s) -> Iterator[str]:
    """Find uppercase characters in the string."""
    for i in range(len(s)):
        if s[i].isupper():
            yield i


def strip(line: str) -> str:
    """
    Remove comments and replace commas from input text
    for a free formatted modflow input file

    Parameters
    ----------
        line : str
            a line of text from a modflow input file

    Returns
    -------
        str : line with comments removed and commas replaced
    """

    for comment_flag in ["//", "#", "!"]:
        line = line.split(comment_flag)[0]
    line = line.strip()
    return line.replace(",", " ")
