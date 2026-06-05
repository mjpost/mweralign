#!/usr/bin/env python3
"""Build script for cross-platform wheels."""

import subprocess
import sys
import os
from pathlib import Path

def run_cmd(cmd):
    """Run command and check for errors."""
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        sys.exit(f"Command failed: {cmd}")

def main():
    """Build wheels for distribution."""
    
    # Clean previous builds
    run_cmd("rm -rf build/ dist/ wheelhouse/ *.egg-info/")
    
    # Build source distribution
    run_cmd("python -m build --sdist")
    
    # Build wheels for current platform
    if "--all-platforms" in sys.argv:
        # Use cibuildwheel for all platforms
        run_cmd("python -m cibuildwheel --output-dir wheelhouse")
    else:
        # Build wheel for current platform only
        run_cmd("python -m build --wheel")
    
    print("\n✅ Build complete!")
    print("📦 Files created:")
    
    for pattern in ["dist/*", "wheelhouse/*"]:
        for file in Path(".").glob(pattern):
            print(f"  - {file}")

if __name__ == "__main__":
    main()