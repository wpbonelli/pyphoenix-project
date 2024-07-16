from flopy4.array import MFArray
from flopy4.block import MFBlock, MFBlocks
from flopy4.list import MFList
from flopy4.scalar import MFDouble, MFFilename, MFInteger, MFKeyword


class PrpOptionsBlock(MFBlock):
    boundnames = MFKeyword()
    print_input = MFKeyword()
    dev_exit_solve_method = MFKeyword()
    exit_solve_tolerance = MFDouble()
    local_z = MFKeyword()
    extend_tracking = MFKeyword()
    track_file = MFFilename()
    trackcsv_file = MFFilename()
    stoptime = MFDouble()
    stoptraveltime = MFDouble()
    stop_at_weak_sink = MFKeyword()
    istopzone = MFInteger()
    drape = MFKeyword()
    release_times = MFArray()
    release_times_file = MFFilename()
    dev_forceternary = MFKeyword()


class PrpDimensionsBlock(MFBlock):
    nreleasepts = MFInteger()


class PrpPackageDataBlock(MFBlock):
    packagedata = MFList()


class PrpPeriodBlocks(MFBlocks):
    perioddata = None
