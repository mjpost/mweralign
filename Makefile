# Makefile for mweralign
#
#   make           # build the standalone C++ CLI (default)
#   make python    # build/install the Python package (editable, with dev deps)
#   make test      # run the Python test + regression suite
#   make clean     # remove build artifacts

BUILD_DIR    := build
BUILD_TYPE   ?= Release
PYTHON       ?= python3

.PHONY: all build python test clean

# Default target: build the C++ CLI.
all: build

build:
	cmake -S . -B $(BUILD_DIR) -DCMAKE_BUILD_TYPE=$(BUILD_TYPE)
	cmake --build $(BUILD_DIR)

# Build and install the Python package in editable mode with dev dependencies.
python:
	$(PYTHON) -m pip install -e ".[dev]"

# Run the test and regression suite. Depends on the package being importable.
test: python
	$(PYTHON) -m pytest python/tests

clean:
	rm -rf $(BUILD_DIR) dist wheelhouse *.egg-info
