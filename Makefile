# Makefile for mweralign
#
#   make           # build the standalone C++ CLI (default)
#   make python    # build/install the Python package (editable, with dev deps)
#   make test      # run the Python test + regression suite
#   make tag       # tag and push the current release (must be on master)
#   make clean     # remove build artifacts

BUILD_DIR    := build
BUILD_TYPE   ?= Release
PYTHON       ?= python3

# Release version, read from pyproject.toml (the source of truth).
VERSION      := $(shell sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml)
TAG          := v$(VERSION)

.PHONY: all build python test tag clean

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

# Tag the current release (v$(VERSION) from pyproject.toml) and push the tag.
# Refuses to run unless on master with a clean tree and a not-yet-used tag.
tag:
	@branch=$$(git rev-parse --abbrev-ref HEAD); \
	if [ "$$branch" != "master" ]; then \
		echo "Error: must be on master to tag (currently on '$$branch')."; exit 1; \
	fi
	@if [ -n "$$(git status --porcelain)" ]; then \
		echo "Error: working tree is not clean; commit or stash changes first."; exit 1; \
	fi
	@if [ -z "$(VERSION)" ]; then \
		echo "Error: could not read version from pyproject.toml."; exit 1; \
	fi
	@if git rev-parse -q --verify "refs/tags/$(TAG)" >/dev/null; then \
		echo "Error: tag $(TAG) already exists."; exit 1; \
	fi
	git tag -a "$(TAG)" -m "Release $(TAG)"
	git push origin "$(TAG)"

clean:
	rm -rf $(BUILD_DIR) dist wheelhouse *.egg-info
