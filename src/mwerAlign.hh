/* ---------------------------------------------------------------- */
/* Copyright 2003 (c) by RWTH Aachen - Lehrstuhl fuer Informatik VI */
/* Richard Zens                                                     */
/* ---------------------------------------------------------------- */
#ifndef MWERALIGN_HH_
#define MWERALIGN_HH_

#include <map>
#include <set>
#include <sstream>
#include <string>
#include <vector>
#include <iterator>
#include <algorithm>

using namespace std;

typedef std::vector<std::string> Sentence;
typedef vector<Sentence> Text;

inline char mytolower(const char &c) { return tolower(c); }

inline string makelowerstring(const string &s)
{
    string rv(s);
    transform(rv.begin(), rv.end(), rv.begin(), mytolower);
    return rv;
}

inline Sentence makelowersent(const Sentence &s)
{
    Sentence rv(s.size());
    transform(s.begin(), s.end(), rv.begin(), makelowerstring);
    return rv;
}

template <class T> inline void makelowertext(const T &in, T &out)
{
    out.resize(in.size());
    transform(in.begin(), in.end(), out.begin(), makelowersent);
}

inline Sentence makeSent(const string &s)
{
    Sentence rv;
    istringstream is(s);
    copy(istream_iterator<string>(is), istream_iterator<string>(), back_inserter(rv));
    return rv;
}

class MwerSegmenter
{
  public:
    /** A candidate (hypothesis) sentence */
    typedef Sentence hyptype;

    /** A candidate (hypothesis) corpus */
    typedef Text HypContainer;

    /** Multiple reference sentences for a candidate sentence */
    typedef vector<hyptype> mreftype;

    /** Corpus multiple reference sentences for a candidate corpus */
    typedef vector<mreftype> MRefContainer;

    /** General evaluation exception */
    class EvaluationException
    {
    };

    /** Exception: Thrown by evaluate() when called without having properly initialized references **/
    class InvalidReferencesException : public EvaluationException
    {
    };

    /** Exception: Thrown if this kind of evaluation is not possible (e.g. _abs with BLEU, NIST) **/
    class InvalidMethodException : public EvaluationException
    {
    };

  private:
    /** Init internal reference sentence structures.
     * To be called from loadRefs(), after reference sentences
     * have been loaded.
     *
     * Overwrite this method and not loadRefs() if possible.
     *
     * \return true iff loading was successfull
     **/
    bool initrefs()
    {
        if (mref.empty())
            return (referencesAreOk = false);
        else
            return (referencesAreOk = true);
    }

    double maxER_;
    bool human_;
    double ins_, del_;
    unsigned int segmentationWord;
    mutable unsigned int refLength_;
    mutable unsigned int vocCounter_;
    bool usecase;
    bool referencesAreOk;
    bool segmenting;

    const string underscoreWord = "▁";

    /** Container for the reference sentences **/
    MRefContainer mref;
    mutable map<string, unsigned int> vocMap_;
    mutable map<unsigned int, string> voc_id_to_word_map_;

    mutable set<unsigned int> punctuationSet_;
    mutable vector<unsigned int> boundary;
    mutable vector<unsigned int> sentCosts;

    double computeSpecialWER(const vector<vector<unsigned int>> &ref_ids,
                             const vector<unsigned int> &hyp_ids, unsigned int nSegments) const;
    unsigned int getVocIndex(const string &word) const;
    string getVocWord(const uint id) const;

    unsigned int getSubstitutionCosts(const uint a, const uint b) const;
    unsigned int getInsertionCosts(const uint w) const;
    unsigned int additionalInsertionCosts(const uint, const uint, bool, const uint) const;
    unsigned int getDeletionCosts(const uint w) const;
    void fillPunctuationSet();
    bool isInternal(const uint w) const;

  public:
    MwerSegmenter()
        : maxER_(-1), human_(false), ins_(1), del_(1), refLength_(0), vocCounter_(0), usecase(false),
          referencesAreOk(false), segmenting(false)
    {
        fillPunctuationSet();
    }

    ~MwerSegmenter() {}

    void mwerAlign(const string &ref, const string &hyp, string &result);

    /** return normalized number of errors (= error rate)
     * \param sentence hyps Candidate corpus to evaluate
     **/
    double evaluate(const HypContainer &hyps, ostream &out) const;

    /** write detailed evaluation information to output stream
     * \param out Output stream to write evaluation to
     * \param hyps Candidate corpus to evaluate
     **/
    void detailed_evaluation(ostream &, const HypContainer &) const {};

    /** set flag for case sensitivity
     * \param b \em true: regard case information; \em false: neglect case information
     **/
    void setcase(bool b) { usecase = b; }

    /** set flag for tokenization
     * \param b \em true: Tokenize \b references \em false: do not tokenize references
     **/
    void setsegmenting(bool s) { segmenting = s; }

    /** Load reference sentences from file in mref format
     * (i.e. multiple refererences separated by a '#' in each line)
     * Initialize then all necessary reference data structures.
     * Must be called \b before evaluation.
     *
     * The default implementation loads the sentences into the mref container
     * and calls \see initrefs() afterwards.
     * It is recommended to redefine \see initrefs() instead of loadrefs when inheriting.
     *
     * \param filename MRef file name
     * \return true iff loading was successfull
     **/
    bool loadrefs(const string &filename);

    bool loadrefsFromStream(istream &in);

    /** Load reference sentences from MRefContainer
     * Initialize then all necessary reference data structures.
     * Must be called \b before evaluation.
     *
     * The default implementation loads the sentences into the mref container
     * and calls \see initrefs() afterwards.
     * It is recommended to redefine \see initrefs() instead of loadrefs when inheriting.
     *
     * \param references Reference sentences
     **/

    typedef struct DP_ {
        unsigned int cost;
        unsigned int bp;
    } DP;
    typedef vector<vector<DP>> Matrix;

    void setInsertionCosts(double x) { ins_ = x; }
    void setDeletionCosts(double x) { del_ = x; }
};

std::istream &operator>>(std::istream &in, Sentence &x);
std::ostream &operator<<(std::ostream &out, const Sentence &x);
std::ostream &operator<<(std::ostream &out, const Text &x);
std::istream &operator>>(std::istream &in, Text &x);

#endif
