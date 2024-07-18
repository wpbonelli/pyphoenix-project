from flopy4.block import MFBlock, MFBlocks
from flopy4.package import MFPackage, get_member_blocks


class TestPackage(MFPackage):
    __test__ = False  # tell pytest not to collect

    options = MFBlock()
    package = MFBlock()
    periods = MFBlocks()


def test_get_member_blocks():
    blocks = get_member_blocks(TestPackage)
    assert len(blocks) == 3
    assert isinstance(blocks["options"], MFBlock)
    assert isinstance(blocks["package"], MFBlock)
    assert isinstance(blocks["periods"], MFBlocks)
