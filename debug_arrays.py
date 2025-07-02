#!/usr/bin/env python3

"""Debug script to test the array conversion logic outside Jinja templates."""

import sys
import os
sys.path.insert(0, '/home/wes/dev/pyphoenix-project')

from pathlib import Path
import numpy as np
from flopy.discretization import StructuredGrid
from flopy.discretization.modeltime import ModelTime

from flopy4.mf6.gwf import Chd, Dis, Gwf, Ic, Npf, Oc
from flopy4.mf6.simulation import Simulation
from flopy4.mf6.tdis import Tdis
from flopy4.mf6.filters import _unstructure_array_lazy, _prepare_chd_lazy, _prepare_tdis_lazy
from flopy4.mf6.spec import get_blocks


def test_chd_conversion():
    """Test CHD array conversion step by step."""
    print("=== Testing CHD Conversion ===")
    
    # Set up the same model as in the test
    time = ModelTime(perlen=[1.0], nstp=[1], tsmult=[1.0])
    grid = StructuredGrid(nlay=1, nrow=10, ncol=10)
    sim = Simulation(tdis=time, name="test")
    gwf = Gwf(parent=sim, dis=grid, name="gwf")
    chd = Chd(parent=gwf, head={0: {(0, 0, 0): 1.0, (0, 9, 9): 0.0}})
    
    print(f"Grid shape: nlay={grid.nlay}, nrow={grid.nrow}, ncol={grid.ncol}")
    print(f"Grid nnodes: {grid.nnodes}")
    
    # Test the coordinate conversion manually
    print(f"Manual coord conversion:")
    print(f"  (0, 0, 0) -> node {0 * grid.nrow * grid.ncol + 0 * grid.ncol + 0} = {0}")
    print(f"  (0, 9, 9) -> node {0 * grid.nrow * grid.ncol + 9 * grid.ncol + 9} = {9 * 10 + 9} = {99}")
    
    print(f"CHD head array exists: {chd.head is not None}")
    if chd.head is not None:
        print(f"CHD head shape: {chd.head.shape}")
        print(f"CHD head dims: {chd.head.dims}")
        print(f"CHD head data type: {type(chd.head.data)}")
        print(f"CHD head data shape: {chd.head.data.shape}")
        
        # Check some specific values
        print(f"Head values at specific nodes:")
        print(f"  chd.head[0, 0] = {chd.head[0, 0]}")
        print(f"  chd.head[0, 9] = {chd.head[0, 9]}")
        print(f"  chd.head[0, 99] = {chd.head[0, 99]}")
        
        # Check the actual data more systematically
        print(f"Non-NaN values in head array:")
        for period in range(chd.head.shape[0]):
            for node in range(chd.head.shape[1]):
                val = chd.head[period, node]
                if not np.isnan(val):
                    print(f"  Period {period}, Node {node}: {val}")
        
        # Test the conversion
        result = _unstructure_array_lazy(chd.head)
        print(f"Conversion result: {result}")
        
        # Test with the CHD DFN block
        blocks = get_blocks(chd.dfn)
        period_block = blocks.get("period", {})
        print(f"Period block fields: {list(period_block.keys())}")
        
        # Test the CHD preparation
        chd_result = _prepare_chd_lazy(chd, period_block)
        print(f"CHD preparation result: {chd_result}")


def test_tdis_conversion():
    """Test TDIS array conversion step by step."""
    print("\n=== Testing TDIS Conversion ===")
    
    # Set up TDIS
    time = ModelTime(perlen=[1.0], nstp=[1], tsmult=[1.0])
    tdis = Tdis.from_time(time)
    
    print(f"TDIS perlen array exists: {tdis.perlen is not None}")
    if tdis.perlen is not None:
        print(f"TDIS perlen shape: {tdis.perlen.shape}")
        print(f"TDIS perlen dims: {tdis.perlen.dims}")
        print(f"TDIS perlen data type: {type(tdis.perlen.data)}")
        print(f"TDIS perlen values: {tdis.perlen.values}")
        
        # Test the conversion
        result = _unstructure_array_lazy(tdis.perlen)
        print(f"Perlen conversion result: {result}")
        
        # Test with the TDIS DFN block
        blocks = get_blocks(tdis.dfn)
        perioddata_block = blocks.get("perioddata", {})
        print(f"Perioddata block fields: {list(perioddata_block.keys())}")
        
        # Test the TDIS preparation
        tdis_result = _prepare_tdis_lazy(tdis, perioddata_block)
        print(f"TDIS preparation result: {tdis_result}")


if __name__ == "__main__":
    test_chd_conversion()
    test_tdis_conversion()
