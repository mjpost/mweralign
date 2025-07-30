/* ---------------------------------------------------------------- */
/* Copyright 2003 (c) by RWTH Aachen - Lehrstuhl fuer Informatik VI */
/* Richard Zens                                                     */
/* ---------------------------------------------------------------- */
#include "mwerAlign.hh"
#include <fstream>
#include <iostream>
#include <sstream>

using namespace std;


std::istream &operator>>(std::istream &in, Sentence &x)
{
    x.clear();
    std::string line;
    getline(in, line);
    std::istringstream is(line);
    typedef std::istream_iterator<std::string> iter;
    std::copy(iter(is), iter(), std::back_inserter(x));
    return in;
}

std::ostream &operator<<(std::ostream &out, const Sentence &x)
{
    std::copy(x.begin(), x.end(), std::ostream_iterator<std::string>(out, " "));
    return out;
}

std::ostream &operator<<(std::ostream &out, const Text &x)
{
  for (Text::const_iterator i = x.begin(); i != x.end(); ++i) {
        out << *i << "\n";
    }
    out << std::flush;
    return out;
}

std::istream &operator>>(std::istream &in, Text &x)
{
    std::string line, w;
    while (getline(in, line)) {
        std::istringstream is(line);
        x.push_back(Sentence());
        while (is >> w)
            x.back().push_back(w);
    }
    return in;
}


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

        hyptype h_m = makeSent(usecase ? line : makelowerstring(line));
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
    std::string wlc = makelowerstring(word);
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
std::string MwerSegmenter::getVocWord(const uint id) const
{
    std::map<unsigned int, std::string>::const_iterator p = voc_id_to_word_map_.find(id);
    if (p != voc_id_to_word_map_.end())
        return p->second;
    return "";
}

/*
 * Substitution cost.
 */
unsigned int MwerSegmenter::getSubstitutionCosts(const uint a, const uint b) const
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

unsigned int MwerSegmenter::getDeletionCosts(const uint w) const
{
    /** additional costs for deletion if the word is a punctuation **/
    if (!human_ || (punctuationSet_.find(w) == punctuationSet_.end()))
        return (unsigned int)(del_);
    else
        return 2;
}

unsigned int MwerSegmenter::getInsertionCosts(const uint w) const
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
bool MwerSegmenter::isInternal(const uint w) const
{
    // get the first character of the word and compare it to underscoreWord
    std::string word = getVocWord(w);

    bool result = (word.length() > 0 && word[0] != underscoreWord[0]);
    // if (result)
    // std::cerr << "isInternal(" << word << "): " << result << std::endl;
    return result;
}

unsigned int MwerSegmenter::additionalInsertionCosts(const uint ref_next, const uint ref_prev, bool is_new_sent,
                                                     const uint w) const
{
    // large cost if we're putting an internal word at the start of a sentence
    if (is_new_sent && isInternal(w)) {
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
    std::vector<std::vector<DP>> m(R), mnew(R);
    boundary.resize(S + 1);
    sentCosts.resize(S + 1);
    //   unsigned int cSUB = 1, cDEL=(unsigned int)(del_), cINS=(unsigned int)(ins_);
    unsigned int epsilon = 0;
    unsigned int s, sub, del, ins, k, min = 10000000, argmin = 0, bestRef = 0;
    bool merge;

    if (J == 0)
        return 0;

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
                    float extra_cost = (segmenting && is_new_sent && isInternal(hyp_ids[j - 1]) ? 1000 : 0);

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

