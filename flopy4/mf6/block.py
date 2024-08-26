from typing import Optional

from flopy4.context import Context


class Block(Context):
    """
    A MODFLOW 6 input block.
    """

    def __init__(
        self,
        name: Optional[str] = None,
        index: Optional[int] = None,
        parent: Optional[Context] = None,
    ):
        super().__init__(name, parent)
        self.index = index
