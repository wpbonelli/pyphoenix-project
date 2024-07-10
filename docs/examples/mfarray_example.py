# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: light
#       format_version: '1.5'
#       jupytext_version: 1.16.2
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---

# This example demonstrates the `NumpyBackedArray` class.

# +
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from flopy4.nparray import NumPyBackedArray
# -

# non-layered data

internal = Path("data/mfarray/internal.txt")
pth = internal.parent
constant = pth / "constant.txt"
external = pth / "external.txt"
shape = (1000, 100)

# Open and load a NumPy array representation

fhandle = open(internal)
imfa = NumPyBackedArray.load(fhandle, pth, shape)

# Get values

ivals = imfa.values
plt.imshow(ivals[0:100])
plt.colorbar();

print(imfa.how)
print(imfa.factor)

imfa._flat

# adjust values

imfa[0:8] = 5000
ivals2 = imfa.values
plt.imshow(ivals2[0:100])
plt.colorbar();

fhandle = open(constant)
cmfa = NumPyBackedArray.load(fhandle, pth, shape)
cvals = cmfa.values
plt.imshow(cvals[0:100])
plt.colorbar();

print(cmfa._flat)

cmfa.how

# Slicing and multiplication

cmfa[0:10] *= 5
plt.imshow(cmfa[0:100])
plt.colorbar();

cmfa.how

cvals2 = cmfa.values
cmfa._flat

# External

fhandle = open(external)
emfa = NumPyBackedArray.load(fhandle, pth, shape)
evals = emfa.values
evals

plt.imshow(emfa[0:100])
plt.colorbar();

emfa.how, emfa.factor

emfa **= 6
evals2 = emfa.values
evals2

plt.imshow(emfa[0:100])
plt.colorbar();

# #### Layered data
# layered data

ilayered = pth / "internal_layered.txt"
clayered = pth / "constant_layered.txt"
mlayered = pth / "mixed_layered.txt"  # (internal, constant, external)

fhandle = open(ilayered)
shape = (3, 1000, 100)
ilmfa = NumPyBackedArray.load(fhandle, pth, shape, layered=True)
vals = ilmfa.values

ilmfa._flat  # internal storage

vals = ilmfa.values
vals

# +
fig, axs = plt.subplots(ncols=3, figsize=(12, 4))
vmin, vmax = np.min(vals), np.max(vals)
for ix, v in enumerate(vals):
    im = axs[ix].imshow(v[0:100], vmin=vmin, vmax=vmax)
    axs[ix].set_title(f"layer {ix + 1}")
    
fig.subplots_adjust(right=0.8)
cbar_ax = fig.add_axes([0.85, 0.15, 0.05, 0.7])
fig.colorbar(im, cax=cbar_ax);
# -

ilmfa.how

ilmfa.factor

# Adjust array values using ufuncs

ilmfa[0, 0:10, 0:60] += 350
ilmfa[1, 10:20, 20:80] += 350  
ilmfa[2, 20:30, 40:] += 350

# +
vals = ilmfa.values
fig, axs = plt.subplots(ncols=3, figsize=(12, 4))
vmin, vmax = np.min(vals), np.max(vals)
for ix, v in enumerate(vals):
    im = axs[ix].imshow(v[0:100], vmin=vmin, vmax=vmax)
    axs[ix].set_title(f"layer {ix + 1}")
    
fig.subplots_adjust(right=0.8)
cbar_ax = fig.add_axes([0.85, 0.15, 0.05, 0.7])
fig.colorbar(im, cax=cbar_ax);
# -

# Layered constants

fhandle = open(clayered)
shape = (3, 1000, 100)
clmfa = NumPyBackedArray.load(fhandle, pth, shape, layered=True)

clmfa._flat

for obj in clmfa._flat:
    print(obj._flat)
clmfa.how

vals = clmfa.values

# +
fig, axs = plt.subplots(ncols=3, figsize=(12, 4))
vmin, vmax = np.min(vals), np.max(vals)
for ix, v in enumerate(vals):
    im = axs[ix].imshow(v[0:100], vmin=vmin, vmax=vmax)
    axs[ix].set_title(f"layer {ix + 1}")
    
fig.subplots_adjust(right=0.8)
cbar_ax = fig.add_axes([0.85, 0.15, 0.05, 0.7])
fig.colorbar(im, cax=cbar_ax);
# -

# Adjust a slice of the layered array

clmfa[0, 0:80, 20:80] += 10
clmfa[1] += 5
clmfa[2] += 2

clmfa.how

# verify that the constants haven't 
# been converted to array internally
for obj in clmfa._flat[1:]:
    print(obj._flat)

vals = clmfa.values

# +
fig, axs = plt.subplots(ncols=3, figsize=(12, 4))
vmin, vmax = np.min(vals), np.max(vals)
for ix, v in enumerate(vals):
    im = axs[ix].imshow(v[0:100], vmin=vmin, vmax=vmax)
    axs[ix].set_title(f"layer {ix + 1}")
    
fig.subplots_adjust(right=0.8)
cbar_ax = fig.add_axes([0.85, 0.15, 0.05, 0.7])
fig.colorbar(im, cax=cbar_ax);
# -

# Mixed data source Layered

fhandle = open(mlayered)
shape = (3, 1000, 100)
mlmfa = NumPyBackedArray.load(fhandle, pth, shape, layered=True)

mlmfa.how

mlmfa._flat

vals = mlmfa.values
vals = np.where(vals <= 0, vals.mean(), vals)
mlmfa[:] = vals

# +
fig, axs = plt.subplots(ncols=3, figsize=(12, 4))
vmin, vmax = np.min(vals), np.max(vals)
for ix, v in enumerate(vals):
    im = axs[ix].imshow(v[0:100], vmin=vmin, vmax=vmax)
    axs[ix].set_title(f"layer {ix + 1}")
    
fig.subplots_adjust(right=0.8)
cbar_ax = fig.add_axes([0.85, 0.15, 0.05, 0.7])
fig.colorbar(im, cax=cbar_ax);
# -

# ### Using numpy mathematical functions with NumPyBackedArray
#
# Numpy support has been added to NumPyBackedArray though the __array_ufunc__ mixin method. This method allows us to send NumPyBackedArray to numpy standard functions like `np.log()`, `np.sin()`, `np.pow()`, etc ...

mlmfa = np.log(mlmfa)
mlmfa

vals = mlmfa.values
vals

# +
fig, axs = plt.subplots(ncols=3, figsize=(12, 4))
vmin, vmax = np.min(vals), np.max(vals)
for ix, v in enumerate(vals):
    im = axs[ix].imshow(v[0:100], vmin=vmin, vmax=vmax)
    axs[ix].set_title(f"layer {ix + 1}")
    
fig.subplots_adjust(right=0.8)
cbar_ax = fig.add_axes([0.85, 0.15, 0.05, 0.7])
fig.colorbar(im, cax=cbar_ax);
# -

# We can also get statistical information about the data, like `sum()`, `mean()`, `max()`, `min()`, `median`, `std()`

mlmfa.sum()

mlmfa.min(), mlmfa.mean(), mlmfa.max()


