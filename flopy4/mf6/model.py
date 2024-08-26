from flopy4.context import Context
from flopy4.decorators import paired_dir, paired_file
from flopy4.mf6.block import Block
from flopy4.mf6.io import mf6io
from flopy4.mf6.package import Package


@mf6io
@paired_file(attr_name="filename")
@paired_dir(attr_name="workspace")
class Model(Context):
    # TODO: anything needed?
    pass

    @property
    def blocks(self):
        return {
            n: c for n, c in self.components.items() if isinstance(c, Block)
        }

    @property
    def packages(self):
        return {
            n: c for n, c in self.components.items() if isinstance(c, Package)
        }
