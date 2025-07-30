#!/usr/bin/env python3

"""
Copyright (c) 2025 Matt Post

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

from pybind11.setup_helpers import Pybind11Extension, build_ext
from pybind11 import get_cmake_dir
import pybind11
from setuptools import setup, Extension
import glob

# Define the extension module
ext_modules = [
    Pybind11Extension(
        "mweralign._mweralign",
        [
            "src/mwerAlign.cc",
            "bindings/bindings.cpp",  # New bindings file
        ],
        include_dirs=[
            "src/",
            pybind11.get_include(),
        ],
        language='c++',
        cxx_std=11,
    ),
]

setup(
    ext_modules=ext_modules,
    cmdclass={"build_ext": build_ext},
    zip_safe=False,
)
