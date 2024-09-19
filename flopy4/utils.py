def depth(d):
    """
    Get the nesting depth of a dictionary.
    Referenced from https://stackoverflow.com/a/23499101/6514033.
    """
    if isinstance(d, dict):
        return 1 + (max(map(depth, d.values())) if d else 0)
    return 0


def find_upper(s):
    for i in range(len(s)):
        if s[i].isupper():
            yield i


def flatten(d):
    if isinstance(d, (tuple, list)):
        for x in d:
            yield from flatten(x)
    else:
        yield d


def strip(line):
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


def str2bool(v):
    return v.lower() in ("yes", "true", "t", "1")
