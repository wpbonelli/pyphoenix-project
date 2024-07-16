from block_example import (
    PrpDimensionsBlock,
    PrpOptionsBlock,
    PrpPackageDataBlock,
)

from flopy4.package import MFPackage


class PrpPackage(MFPackage):
    options = PrpOptionsBlock
    dimensions = PrpDimensionsBlock
    packagedata = PrpPackageDataBlock

    nreleasepts
    nreleasepts
