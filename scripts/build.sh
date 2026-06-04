#!/bin/bash
set -e

echo "Building C++ extensions..."
python setup.py build_ext --inplace

echo "Build complete!"
