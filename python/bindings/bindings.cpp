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
        .def("set_legacy_penalty", &MwerSegmenter::setLegacyPenalty,
             "TEMPORARY: restore the pre-fix penalty behavior (apply the "
             "segment-initial internal-word penalty even for untokenized input)",
             py::arg("enable"))
        .def("set_forbid_midword_boundary", &MwerSegmenter::setForbidMidwordBoundary,
             "Forbid segmentation boundaries that would start a non-final "
             "segment on a word-internal, non-punctuation piece (no mid-word "
             "cuts). Off by default.",
             py::arg("enable"))
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
        }, "Evaluate hypothesis against loaded references")
        .def("set_collect_trace", &MwerSegmenter::setCollectTrace,
             "Enable/disable collection of the alignment trace (boundary DP "
             "table). Disabled by default; off-path is free.",
             py::arg("enable"))
        .def("collect_trace", &MwerSegmenter::collectTrace,
             "Whether trace collection is currently enabled")
        .def("set_collect_cells", &MwerSegmenter::setCollectCells,
             "Enable/disable per-cell cost recording (O(J*I*R); diagnostic "
             "inputs only). Boundary tables are recorded independently.",
             py::arg("enable"))
        .def("collect_cells", &MwerSegmenter::collectCells,
             "Whether per-cell cost recording is currently enabled")
        .def("trace_boundary_cost", &MwerSegmenter::traceBoundaryCost,
             "BC[j][s]: best total cost ending segment s at hyp position j")
        .def("trace_boundary_bp", &MwerSegmenter::traceBoundaryBP,
             "BP[j][s]: backpointer to where segment s-1 ends")
        .def("trace_boundary_ref", &MwerSegmenter::traceBoundaryRef,
             "BR[j][s]: best reference index for the segment ending at j")
        .def("boundaries", &MwerSegmenter::boundaries,
             "Chosen segment boundaries (hyp positions) from the last alignment")
        .def("segment_costs", &MwerSegmenter::segmentCosts,
             "Cumulative per-segment costs from the last alignment")
        .def("trace_cells", [](const MwerSegmenter& self) {
            py::list out;
            for (const auto& c : self.traceCells()) {
                out.append(py::make_tuple(
                    c.j, c.i, c.ref, c.del_cost, c.ins_cost, c.sub_cost,
                    c.chosen, c.extra, std::string(1, c.op), c.is_new_sent));
            }
            return out;
        }, "Per-cell DP costs from the last traced alignment as a list of "
           "(j, i, ref, del, ins, sub, chosen, extra, op, is_new_sent) tuples");
}
