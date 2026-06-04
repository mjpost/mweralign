/*
 * Copyright (c) 2025 Matt Post
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/iostream.h>
#include "mwerAlign.hh"

namespace py = pybind11;

PYBIND11_MODULE(_mweralign, m) {
    m.doc() = "Minimum Word Error Rate Alignment";
    
    py::class_<MwerSegmenter>(m, "MwerSegmenter")
        .def(py::init<>())
        .def("mwerAlign", [](MwerSegmenter& self, const std::string& ref, const std::string& hyp) -> std::string {
            std::string result;
            self.mwerAlign(ref, hyp, result);
            return result;
        })
        .def("set_tokenized", &MwerSegmenter::setsegmenting,
             "Set whether the references are tokenized",
             py::arg("tokenize"))
        .def("loadrefs", &MwerSegmenter::loadrefs,
             "Load references from file",
             py::arg("filename"))
        .def("loadrefsFromStream", [](MwerSegmenter& self, const std::string& content) {
            std::istringstream stream(content);
            return self.loadrefsFromStream(stream);
        }, "Load references from string content")
        .def("evaluate", [](const MwerSegmenter& self, const TextNS::SimpleText& hyps) {
            std::ostringstream out;
            double result = self.evaluate(hyps, out);
            return py::make_tuple(result, out.str());
        }, "Evaluate hypothesis against loaded references");
}
