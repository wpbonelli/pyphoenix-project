
from contextlib import contextmanager
from typing import Literal


ArrayFormat = Literal["list", "grid", "layer"]


@contextmanager
def output_context(array_format: ArrayFormat):
    pass


with output_context(array_format={"evt": "array", "wel": "grid"}):
    ...

with output_context(array_format={"array": ["evt"], "grid": ["wel"]}):
    ...
