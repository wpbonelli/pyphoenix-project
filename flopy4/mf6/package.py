from flopy4.context import Context
from flopy4.decorators import paired_file
from flopy4.mf6.block import Block
from flopy4.mf6.io import mf6io


@mf6io
@paired_file(attr_name="filename")
class Package(Context):
    # TODO: anything needed?
    pass

    @property
    def blocks(self):
        return {
            n: c for n, c in self.components.items() if isinstance(c, Block)
        }
