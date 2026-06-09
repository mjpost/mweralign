/* ---------------------------------------------------------------- */
/* Copyright 2003 (c) by RWTH Aachen - Lehrstuhl fuer Informatik VI */
/* Richard Zens                                                     */
/* ---------------------------------------------------------------- */
#include "mwerAlign.hh"
#include <fstream>
#include <iostream>
#include <sstream>

// Branch hint so the opt-in trace checks in the hot DP loop are statically
// predicted not-taken and cost effectively nothing when tracing is disabled.
#if defined(__GNUC__) || defined(__clang__)
#define MWER_UNLIKELY(x) (__builtin_expect(!!(x), 0))
#else
#define MWER_UNLIKELY(x) (x)
#endif

using namespace std;

std::istream &operator>>(std::istream &in, Text &x);

/** Load reference sentences from MRefContainer
 * Initialize then all necessary reference data structures.
 * Must be called \b before evaluation.
 *
 * The default implementation loads the sentences into the mref container
 * and calls \see initrefs() afterwards.
 * It is recommended to redefine \see initrefs() instead of loadrefs when inheriting.
 *
 * \param references Reference sentences
 */
void MwerSegmenter::mwerAlign(const std::string &ref, const std::string &hyp, std::string &result)
{
    std::istringstream strRef(ref), strHyp(hyp);
    loadrefsFromStream(strRef);
    setcase(false);

    Text hyps;
    strHyp >> hyps;
    std::ostringstream strOut;
    double unsegmentedWER = 100.0 * evaluate(hyps, strOut);
    std::cerr << "AS-WER (automatic segmentation mWER): " << unsegmentedWER << std::endl;
    result += strOut.str();
}

/**
 * Load reference sentences from file in mref format
 * (i.e. multiple refererences separated by a '#' in each line)
 * Initialize then all necessary reference data structures.
 */
bool MwerSegmenter::loadrefs(const std::string &filename)
{
    std::cerr << "loading reference file: " << filename << " case sensitive: " << usecase << std::endl;
    std::ifstream in(filename.c_str());
    if (!in)
        return (referencesAreOk = false);
    return loadrefsFromStream(in);
}

bool MwerSegmenter::loadrefsFromStream(std::istream &in)
{
    std::cerr << "loading reference file from stream: case sensitive = " << usecase << std::endl;
    mref.clear();

    std::string line, w;
    while (getline(in, line)) {
        mreftype refs;
        hyptype h;

        // std::cerr << "Read line: " << line << std::endl;

        hyptype h_m = TextNS::makeSent(usecase ? line : TextNS::makelowerstring(line));
        for (hyptype::const_iterator i = h_m.begin(); i != h_m.end(); ++i) {
            // multiple references are delimited by ### (TODO(MJ): let's use a tab!
            if (*i == "###") {
                if (!h.empty())
                    refs.push_back(h);

                h.clear();
            } else {
                h.push_back(*i);
            }
        }

        if (!h.empty())
            refs.push_back(h);

        // An empty reference line still denotes a segment. Preserve it as a
        // single empty reference so that evaluate() emits a segmentation marker
        // for it; otherwise the segment count (mref.size()) and the number of
        // markers in ref_ids drift apart, corrupting the backtrace and causing
        // a segmentation fault (issue #1).
        if (refs.empty())
            refs.push_back(hyptype());

        mref.push_back(refs);
    }

    /* prepare tables and hashes */
    return initrefs();
}

double MwerSegmenter::evaluate(const HypContainer &hyps, std::ostream &out) const
{
    size_t num_hyps = hyps.size();
    unsigned int epsilon = 0;
    double rv = 0;
    std::vector<std::vector<unsigned int>> ref_ids;
    std::vector<unsigned int> hyp_ids;
    std::vector<std::string> stringB;

    /** NOTE: different segments can have different number of references!
     -> some sents must have "double" same references, before this can be used! **/
    ref_ids.resize(mref[0].size());
    for (size_t i = 0; i < mref.size(); ++i) {
        // Find the max length of the references
        unsigned int maxRefLength = 0;
        for (HypContainer::const_iterator r = mref[i].begin(); r != mref[i].end(); ++r) {
            if (r->size() > maxRefLength)
                maxRefLength = r->size();
        }

        for (size_t r = 0; r < mref[i].size(); ++r) {
            for (size_t k = 0; k < maxRefLength; ++k) {
                if (k < mref[i][r].size())
                    (ref_ids[r]).push_back(getVocIndex(mref[i][r][k]));
                else
                    (ref_ids[r]).push_back(epsilon);
            }
            (ref_ids[r]).push_back(segmentationWord);
        }
    }

    for (size_t i = 0; i < num_hyps; ++i) {
        for (size_t j = 0; j < hyps[i].size(); ++j) {
            hyp_ids.push_back(getVocIndex(hyps[i][j]));
            stringB.push_back(hyps[i][j]);
        }
    }

    // compute the edit distance
    rv = computeSpecialWER(ref_ids, hyp_ids, mref.size());

    size_t beg = 1;
    size_t end = 0;

    // Ofile segOut("__segments");
    for (size_t s = 2; s < boundary.size(); ++s) {
        end = boundary[s];
        size_t sentLength = 0;
        for (size_t j = beg; j <= std::min(end, stringB.size()); ++j) {
            out << stringB[j - 1] << " ";
            ++sentLength;
        }
        out << "\n";
        double thisSentCosts = double(sentCosts[s - 1] - sentCosts[s - 2]) / double(sentLength);
        if ((maxER_ >= 0) && (thisSentCosts > maxER_)) {
            std::cerr << "WARNING: check the alignment for segment " << s - 1 << " manually (WER: " << thisSentCosts
                      << " )!\n";
        }
        beg = end + 1;
    }
    // for the last segment:
    size_t sentLength = 0;
    for (size_t j = beg; j <= stringB.size(); ++j) {
        out << stringB[j - 1] << " ";
        ++sentLength;
    }
    double thisSentCosts =
        double(sentCosts[sentCosts.size() - 1] - sentCosts[sentCosts.size() - 2]) / double(sentLength);

    if ((maxER_ >= 0) && (thisSentCosts > maxER_)) {
        std::cerr << "WARNING: check the alignment for segment " << sentCosts.size() - 1
                  << " manually (WER: " << thisSentCosts << " )!\n";
    }
    return rv / refLength_;
}

/*
 * Return the vocabulary ID of a word, assigning the ID if necessary.
 * TODO(MJP): seems better to just overload operator[]?
 */
unsigned int MwerSegmenter::getVocIndex(const std::string &word) const
{
    std::string wlc = TextNS::makelowerstring(word);
    std::map<std::string, unsigned int>::const_iterator p = vocMap_.find(wlc);
    if (p != vocMap_.end())
        return p->second;
    ++vocCounter_;
    vocMap_[wlc] = vocCounter_;
    voc_id_to_word_map_[vocCounter_] = wlc;
    return vocCounter_;
}

/*
 * Return the vocabulary word given an ID.
 */
std::string MwerSegmenter::getVocWord(const unsigned int id) const
{
    std::map<unsigned int, std::string>::const_iterator p = voc_id_to_word_map_.find(id);
    if (p != voc_id_to_word_map_.end())
        return p->second;
    return "";
}

/*
 * Substitution cost.
 */
unsigned int MwerSegmenter::getSubstitutionCosts(const unsigned int a, const unsigned int b) const
{
    if (a == b)
        return 0;
    if (!human_)
        return 1;

    bool aIsPunc = (punctuationSet_.find(a) != punctuationSet_.end());
    bool bIsPunc = (punctuationSet_.find(b) != punctuationSet_.end());
    if (aIsPunc && bIsPunc)
        return 1;
    if (aIsPunc || bIsPunc)
        return 2;
    return 1;
}

unsigned int MwerSegmenter::getDeletionCosts(const unsigned int w) const
{
    /** additional costs for deletion if the word is a punctuation **/
    if (!human_ || (punctuationSet_.find(w) == punctuationSet_.end()))
        return (unsigned int)(del_);
    else
        return 2;
}

unsigned int MwerSegmenter::getInsertionCosts(const unsigned int w) const
{
    /** additional costs for insertion if the word is a punctuation **/
    if (!human_ || (punctuationSet_.find(w) == punctuationSet_.end()))
        return (unsigned int)(ins_);
    else
        return 2;
}

/**
 * Checks whether a token is word-internal. Under default SPM settings, word-internal tokens
 * have no underscore prefix.
 *
 * TODO(MJP): generalize
 */
bool MwerSegmenter::isInternal(const unsigned int w) const
{
    // get the first character of the word and compare it to underscoreWord
    std::string word = getVocWord(w);

    bool result = (word.length() > 0 && word[0] != underscoreWord[0]);
    // if (result)
    // std::cerr << "isInternal(" << word << "): " << result << std::endl;
    return result;
}

/**
 * Whether a piece is a word-internal *word* fragment: internal (lacks the
 * leading word marker) AND not pure punctuation. Pure-punctuation pieces (e.g.
 * ".", "...", ".\"") legitimately attach to the previous token and are not the
 * mid-word cuts the boundary constraint targets, so they are excluded.
 */
bool MwerSegmenter::isInternalWord(const unsigned int w) const
{
    if (!isInternal(w))
        return false;
    const std::string word = getVocWord(w);
    for (unsigned char c : word) {
        // A non-ASCII byte (a multibyte letter/CJK char) or an ASCII
        // alphanumeric means this piece carries word material.
        if (c >= 128 || std::isalnum(c))
            return true;
    }
    return false; // all bytes are ASCII punctuation/symbols
}

unsigned int MwerSegmenter::additionalInsertionCosts(const unsigned int ref_next, const unsigned int ref_prev, bool is_new_sent,
                                                     const unsigned int w) const
{
    // large cost if we're putting an internal word at the start of a sentence.
    // This only makes sense when the input is tokenized (e.g. with SentencePiece),
    // where word-internal pieces lack the leading marker. With plain whitespace
    // input every word looks "internal" (isInternal() == true), so without the
    // segmenting guard this penalty would fire on every segment-initial insertion
    // and corrupt the alignment. The legacyPenalty_ flag intentionally drops the
    // guard to reproduce the pre-fix (paper) behavior.
    if ((segmenting || legacyPenalty_) && is_new_sent && isInternal(w)) {
        return 1000;
    }

    return 0;
}

/*
 * Compute the WER of the stream of hyp IDS against the set of references.
 */
double MwerSegmenter::computeSpecialWER(const std::vector<std::vector<unsigned int>> &ref_ids,
                                        const std::vector<unsigned int> &hyp_ids, unsigned int nSegments) const
{
    unsigned int R = ref_ids.size();
    unsigned int I = ref_ids[0].size(); // the length is the same for all references due to epsilon entries
    unsigned int J = hyp_ids.size();
    unsigned int S = nSegments;
    std::vector<std::vector<unsigned int>> BP(J + 1), BC(J + 1);
    std::vector<std::vector<unsigned short>> BR(J + 1);
    // Index 0 of the backpointer tables is never written in the main loop (which
    // runs j = 1..J), but the backtracking below can follow a backpointer to
    // hyp-position 0 while segments remain. Pre-size row 0 so that access is
    // in-bounds (and yields a benign 0) instead of reading an empty vector and
    // crashing -- this happens with the legacy penalty on long merged inputs.
    BP[0].resize(S + 1);
    BC[0].resize(S + 1);
    BR[0].resize(S + 1);
    std::vector<std::vector<DP>> m(R), mnew(R);
    boundary.resize(S + 1);
    sentCosts.resize(S + 1);
    //   unsigned int cSUB = 1, cDEL=(unsigned int)(del_), cINS=(unsigned int)(ins_);
    unsigned int epsilon = 0;
    unsigned int s, sub, del, ins, k, min = 10000000, argmin = 0, bestRef = 0;
    bool merge;

    if (J == 0)
        return 0;

    if (MWER_UNLIKELY(collectTrace_)) {
        traceCells_.clear();
        traceBC_.clear();
        traceBP_.clear();
        traceBR_.clear();
    }

    for (size_t r = 0; r < R; ++r) { // initialization along reference axis i for all references
        m[r].resize(I + 1);
        for (size_t i = 0; i <= I; ++i)
            m[r][i].cost = i;
        mnew[r].resize(2);
    }

    for (size_t j = 1; j <= J; ++j) { // main loop over hyp positions j
        BP[j].resize(S + 1);
        BR[j].resize(S + 1);
        BC[j].resize(S + 1);
        s = 0;
        for (size_t r = 0; r < R; ++r) {
            // initialization along axis j for all references
            m[r][0].cost = j - 1;
            m[r][0].bp = 0;
            mnew[r][0].cost = j;
            mnew[r][0].bp = 0;
        }
        // main loop over ref positions i
        for (size_t i = 1; i <= I; ++i) {
            bool is_new_sent = i > 1 && ref_ids[0][i - 2] == segmentationWord;

            if (ref_ids[0][i - 1] == segmentationWord) {
                merge = true;
                min = 100000000;
                argmin = 0;
                bestRef = 0;
            } else {
                merge = false;
            }

            // loop over references
            for (size_t r = 0; r < R; ++r) {
                if (merge || (ref_ids[r][i - 1] == epsilon)) {
                    // on EOS and for padded refs, just move the previous entry up without any additional costs
                    m[r][i - 1] = mnew[r][0];
                } else {
                    // do compute next step in the LEVENSHTEIN distance
                    // add a large cost if this is the start of sentence and the word is internal
                    float extra_cost = ((segmenting || legacyPenalty_) && is_new_sent && isInternal(hyp_ids[j - 1]) ? 1000 : 0);

                    del = mnew[r][0].cost + getDeletionCosts(ref_ids[r][i - 1]) + extra_cost;
                    ins = m[r][i].cost + getInsertionCosts(hyp_ids[j - 1]) +
                          additionalInsertionCosts(ref_ids[r][i], ref_ids[r][i - 1], is_new_sent, hyp_ids[j - 1]) +
                          extra_cost;
                    sub = m[r][i - 1].cost + extra_cost +
                          getSubstitutionCosts(ref_ids[r][i - 1],
                                               hyp_ids[j - 1]); // ((ref_ids[r][i-1]==hyp_ids[j-1]) ? 0 : cSUB);
                                                                //        std::cerr << j << " " << i << "\n";
                    //        std::cerr << del << " " << ins << " " << sub << "\n";
                    if (sub < del) // do not appreciate substitutions (that is why <, not <=)
                        if (sub < ins) {
                            mnew[r][1].cost = sub;
                            mnew[r][1].bp = m[r][i - 1].bp;
                        } else {
                            mnew[r][1].cost = ins;
                            mnew[r][1].bp = m[r][i].bp;
                        }
                    else if (del <= ins) {
                        mnew[r][1].cost = del;
                        mnew[r][1].bp = mnew[r][0].bp;
                    } else {
                        mnew[r][1].cost = ins;
                        mnew[r][1].bp = m[r][i].bp;
                    }
                    m[r][i - 1] = mnew[r][0]; // finalize saving of the previous entry
                    mnew[r][0] = mnew[r][1];  // move the current entry up the stack

                    if (MWER_UNLIKELY(collectCells_)) {
                        // Re-derive the chosen edit op using the same priority
                        // (substitution preferred, then deletion on a tie with
                        // insertion) so the trace matches the selection above.
                        char op;
                        if (sub < del)
                            op = (sub < ins) ? 'S' : 'I';
                        else
                            op = (del <= ins) ? 'D' : 'I';
                        traceCells_.push_back(CellCost{
                            (unsigned int)j, (unsigned int)i, (unsigned int)r,
                            del, ins, sub, mnew[r][1].cost,
                            (unsigned int)extra_cost, op, is_new_sent});
                    }
                }
                if (merge)
                    // segmentation word is the same in all references
                    if (mnew[r][0].cost < min) {
                        min = mnew[r][0].cost;
                        argmin = mnew[r][0].bp;
                        bestRef = r; // HERE: also save "r"  (reference number, to count reference length!)
                    }
            } // end of loop over references

            if (merge) {
                // segment end, merge
                ++s;
                BC[j][s] = min;
                BP[j][s] = argmin;
                BR[j][s] = bestRef;
                //     std::cerr << "MERGE: " << min << " " << argmin << "\n";
                for (size_t r = 0; r < R; ++r) {
                    mnew[r][0].cost = min;
                    mnew[r][0].bp = j;
                }
            }
        } // end of loop over i
        for (size_t r = 0; r < R; ++r) {
            m[r][I] = mnew[r][0]; // make the stack empty by filling in the last values
        }
    }

    if (MWER_UNLIKELY(collectTrace_)) {
        // Snapshot the full boundary DP tables so callers can inspect every
        // competing segment end (not just the one the backtrace selects).
        traceBC_ = BC;
        traceBP_ = BP;
        traceBR_.assign(BR.size(), std::vector<unsigned int>());
        for (size_t jj = 0; jj < BR.size(); ++jj)
            traceBR_[jj].assign(BR[jj].begin(), BR[jj].end());
    }

    // Backtracing from here:
    s = S; // S = total number of segments
    k = J; // J = total number of hypothesis tokens
    unsigned int refNo = 0;
    do {
        boundary[s] = BP[k][s];
        sentCosts[s] = BC[k][s];
        refNo = BR[k][s];
        refLength_ += mref[s - 1][refNo].size(); // add up the length of the best aligned references
        k = BP[k][s];
        s = s - 1;
    } while (s > 0);

    return m[0][I].cost; // total costs - the same for all references (since a merge is always the last step)
}

void MwerSegmenter::fillPunctuationSet()
{
    std::string period = "</s>";
    segmentationWord = getVocIndex(period);
    punctuationSet_.insert(getVocIndex("."));
    punctuationSet_.insert(getVocIndex(","));
    punctuationSet_.insert(getVocIndex(";"));
    punctuationSet_.insert(getVocIndex("?"));
    punctuationSet_.insert(getVocIndex("!"));
    punctuationSet_.insert(getVocIndex("-"));
    punctuationSet_.insert(getVocIndex(":"));
    punctuationSet_.insert(getVocIndex("/"));
    punctuationSet_.insert(getVocIndex(")"));
    punctuationSet_.insert(getVocIndex("("));
    punctuationSet_.insert(getVocIndex("\""));
}