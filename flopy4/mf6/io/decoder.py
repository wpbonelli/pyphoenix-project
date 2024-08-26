import re
from os import linesep
from io import StringIO
from pathlib import Path
from typing import (
    Dict,
    List,
    Optional,
    Tuple,
    get_args,
)

import numpy as np
import pandas as pd

from flopy4.mf6.io.constants import ArrayHow, InOut
from flopy4.param import Array, Choice, Param, Record, Scalar, Table
from flopy4.utils import strip

IPRN = "iprn"


def parse_scalar(s: str, name: Optional[str]) -> Tuple[str, Scalar]:
    name = name.lower() if name else None
    words = strip(s).lower().split()
    nwords = len(words)
    value = words[-1]

    if nwords == 2:
        name_found = words[0]
        if name != name_found.lower():
            raise ValueError(
                f"Names don't match, given '{name}', found '{name_found}'"
            )
    elif nwords == 1:
        if name is None:
            raise ValueError("Anonymous scalar requires an explicit name")
    else:
        raise ValueError(
            f"Expected format 'name value' or 'value', got {' '.join(words)}"
        )

    # try parsing float
    try:
        value = float(value)
    except:
        pass

    # try parsing int
    try:
        value = int(value)
    except:
        pass

    # otherwise it's a keyword
    name = value.lower()

    return name, value


def parse_string(s: str, name: Optional[str]) -> Tuple[str, str]:
    name = name.lower() if name else None
    words = strip(s).lower().split()

    if name is None:
        name = words[0]
    else:
        name_found = words[0]
        if name != name_found.lower():
            raise ValueError(
                f"Names don't match, given '{name}', found '{name_found}'"
            )
    value = [words[1:]]

    return name, value


def parse_filename(s: str, name: Optional[str]) -> Tuple[str, Path]:
    line = strip(s)
    words = line.split()
    nwords = len(words)

    if name is None:
        if nwords != 3:
            raise ValueError(
                "No name provided, "
                "expected space-separated: "
                "1) keyword, "
                f"2) {' or '.join(get_args(InOut))}"
                "3) file path"
            )
    else:
        if nwords == 3:
            name_in = words[0]
            if name != name_in.lower():
                raise ValueError(
                    f"Names don't match, provided '{name}', found '{name_in}'"
                )
            inout = words[1].lower()
            value = words[2].lower()
        elif nwords == 2:
            inout = words[0].lower()
            value = words[1].lower()
        else:
            raise ValueError(
                "Bad format, "
                "expected space-separated: "
                "1) optional keyword, "
                f"2) {' or '.join(get_args(InOut))}"
                "3) file path"
            )
        if inout not in InOut:
            raise ValueError(f"Bad file type: {inout}")

    return name, Path(value).expanduser()


def parse_record(s: str, params: List[str]) -> Dict[str, Scalar]:
    """Parse a record with the given component parameters from a string."""

    record = dict()
    iparam = 0
    nparams = len(params)
    for param_name in params:
        iparam += 1
        split = s.split()
        words = len(param_name)
        head = " ".join(split[:words])
        tail = " ".join(split[words:])
        s = tail
        with StringIO(head) as f:
            if iparam == nparams:
                try:
                    value = parse_scalar(s, param_name)
                except:
                    value = parse_array(s, param_name)
            else:
                s = f.read()
                value = parse_scalar(s, param_name)
            record[param_name] = value

    return record


def parse_array(s: str, name: Optional[str], shape: Tuple[int]):
    lines = strip(s).split(linesep)
    control_line = lines[0]
    control_words = control_line.split()

    if IPRN in control_line:
        idx = control_line.index(IPRN)
        control_line.pop(idx + 1)
        control_line.pop(idx)

    how = ArrayHow.from_string(control_words[0])
    extpath = None
    clpos = 1

    buffer = StringIO()
    buffer.write(s)

    # TODO: handle layered arrays

    if how == ArrayHow.internal:
        value = load_array(buffer)
    elif how == ArrayHow.constant:
        value = float(control_line[clpos])
        clpos += 1
    elif how == ArrayHow.external:
        extpath = Path(control_line[clpos])
        value = load_array(open(extpath))
        clpos += 1
    else:
        raise NotImplementedError(f"Unsupported array representation: {how}")

    buffer.close()

    factor = None
    if len(control_line) > 2:
        factor = float(control_line[clpos + 1])
        value = value * factor

    return value.reshape(shape)


def load_array(f):
    """
    Read a MODFLOW 6 array from an open file
    into a flat `np.ndarray` representation.
    """

    astr = []
    while True:
        pos = f.tell()
        line = f.readline()
        line = strip(line)
        if not re.match("^[0-9. ]+$", line):
            f.seek(pos, 0)
            break
        astr.append(line)

    astr = StringIO(" ".join(astr))
    array = np.genfromtxt(astr).ravel()
    return array


def parse_dataframe(s: str, name: str) -> Tuple[str, pd.DataFrame]:
    pass


def load_param(f, cls) -> Tuple[str, Param]:
    if cls is Scalar:
        return load_scalar(f.readline(), cls)
    if cls is Record:
        return load_record(f.readline(), cls)
    if cls is Choice:
        return load_choice()
    if cls is Array:
        return load_array(f)
    elif cls is Table:
        return load_table(f)


def load_block(f, spec) -> Tuple[str, int, dict]:
    """Load a block."""
    name = None
    index = 0
    found = False
    params = dict()

    while True:
        pos = f.tell()
        line = f.readline()
        if line == "":
            raise ValueError("Early EOF, aborting")
        if line == "\n":
            continue
        words = strip(line).lower().split()
        key = words[0]
        if key == "begin":
            found = True
            name = words[1]
            if len(words) > 2 and str.isdigit(words[2]):
                index = int(words[2])
        elif key == "end":
            break
        elif found:
            param = spec.get(key)
            if param is None:
                continue
            param.block = name
            f.seek(pos)
            ptype = type(param)
            params[param.name] = load_param(f, ptype)

    return name, index, params


def load_package(f, spec) -> dict:
    """Load a package."""
    blocks = dict()

    while True:
        pos = f.tell()
        line = f.readline()
        if line == "":
            break
        if line == "\n":
            continue
        line = strip(line).lower()
        words = line.split()
        key = words[0]
        if key == "begin":
            name = words[1]
            block = spec.get(name, None)
            if block is None:
                continue
            f.seek(pos)
            blocks[name] = load_block(type(block), f)

    return blocks


def load_model(f, spec) -> dict:
    """Load a model."""
    blocks = dict()
    packages = dict()

    while True:
        line = f.readline()
        if line == "":
            break
        if line == "\n":
            continue
        line = strip(line).lower()
        words = line.split()
        # TODO: Temporary code. Reimplement below to load
        #       dfn block specification with MFList support
        if words[0] == "begin":
            if words[1] == "packages":
                # load packages
                count = 0
                while True:
                    count += 1
                    line = f.readline()
                    line = strip(line).lower()
                    words = line.split()
                    if words[0] == "end":
                        break
                    elif len(words) > 1:
                        ptype = words[0]
                        fpth = words[1]
                        # TODO: pname should be type (remove trailing 6)
                        #       if base (not multi-instance see example
                        #       spec/ipkg/gwf_ic.v2.py)
                        if len(words) > 2:
                            pname = words[2]
                        else:
                            pname = f"{ptype}-{count}"
                    package = spec.get(ptype, None)
                    with open(fpth, "r") as f_pkg:
                        packages[pname] = load_package(type(package), f_pkg)
            else:
                # todo load blocks
                pass

    return {**blocks, **packages}


def load_exchange(f, spec) -> dict:
    # todo
    pass


def load_solution(f) -> dict:
    # todo
    pass


def load_simulation(f) -> dict:
    """Load a simulation."""
    blocks = dict()
    packages = dict()
    models = dict()
    exchanges = dict()
    solutions = dict()

    while True:
        # pos = f.tell()
        line = f.readline()
        if line == "":
            break
        if line == "\n":
            continue
        line = strip(line).lower()
        words = line.split()
        # TODO: Temporary code. Reimplement below to load
        #       dfn block specification with MFList support
        if words[0] == "begin":
            if words[1] == "models":
                count = 0
                while True:
                    count += 1
                    line = f.readline()
                    line = strip(line).lower()
                    if line == "":
                        break
                    if line == "\n":
                        continue
                    words = line.split()
                    if words[0] == "end" and words[1] == "models":
                        break
                    elif len(words) > 1:
                        mtype = words[0]
                        fpth = words[1]
                        if len(words) > 2:
                            mname = words[2]
                        else:
                            mname = f"{mtype}-{count}"
                    with open(fpth, "r") as f_model:
                        models[mname] = load(f_model)
            elif words[1] == "exchanges":
                # todo load exchanges
                pass

    return {**blocks, **packages, **models, **exchanges, **solutions}


class MF6DecodeError(ValueError):
    """Subclass of `ValueError` with the following additional properties:

    - msg: The unformatted error message
    - doc: The input file being parsed
    - line: The line producing the error

    """

    def __init__(self, msg, doc, line):
        errmsg = "%s: line %d" % (msg, line)
        ValueError.__init__(self, errmsg)
        self.msg = msg
        self.doc = doc
        self.line = line


class MF6Decoder:
    """
    MF6 input format decoder. Decodes MF6 input file format into
    Python built-in primitives and containers, as well as NumPy
    arrays and Pandas data frames.

    Performs the following translations:

    +-------------------+-----------------------+
    | MF6 Input         | Python                |
    +===================+=======================+
    | keyword           | bool                  |
    +-------------------+-----------------------+
    | integer           | int                   |
    +-------------------+-----------------------+
    | double precision  | float                 |
    +-------------------+-----------------------+
    | string            | str                   |
    +-------------------+-----------------------+
    | filename          | Path                  |
    +-------------------+-----------------------+
    | record            | dict                  |
    +-------------------+-----------------------+
    | keystring         | dict                  |
    +-------------------+-----------------------+
    | array             | np.ndarray            |
    +-------------------+-----------------------+
    | list              | list or pd.DataFrame  |
    +-------------------+-----------------------+
    | block             | dict                  |
    +-------------------+-----------------------+
    | package           | dict                  |
    +-------------------+-----------------------+
    | model             | dict                  |
    +-------------------+-----------------------+
    | exchange          | dict                  |
    +-------------------+-----------------------+
    | solution          | dict                  |
    +-------------------+-----------------------+
    | simulation        | dict                  |
    +-------------------+-----------------------+

    """

    def decode(self, s):
        # todo
        pass


_decoder = MF6Decoder()


def load(f):
    return _decoder.decode(f.read())


def loads(s):
    return _decoder.decode(s)
