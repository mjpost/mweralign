/* ---------------------------------------------------------------- */
/* Copyright 2003 (c) by RWTH Aachen - Lehrstuhl fuer Informatik VI */
/* Richard Zens                                                     */
/* ---------------------------------------------------------------- */
#ifndef MWERALIGN_HH_
#define MWERALIGN_HH_
// #include "Evaluator.hh"
#include "SimpleText2.hh"
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <vector>

using namespace std;

typedef TextNS::SimpleText Text;

class MwerSegmenter
{
  public:
    /** A candidate (hypothesis) sentence */
    typedef TextNS::Sentence hyptype;

    /** A candidate (hypothesis) corpus */
    typedef TextNS::SimpleText HypContainer;

    /** Multiple reference sentences for a candidate sentence */
    typedef std::vector<hyptype> mreftype;

    /** Corpus multiple reference sentences for a candidate corpus */
    typedef std::vector<mreftype> MRefContainer;

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

    const std::string underscoreWord = "▁";

    /** Container for the reference sentences **/
    MRefContainer mref;
    mutable std::map<std::string, unsigned int> vocMap_;
    mutable std::map<unsigned int, std::string> voc_id_to_word_map_;

    mutable std::set<unsigned int> punctuationSet_;
    mutable std::vector<unsigned int> boundary;
    mutable std::vector<unsigned int> sentCosts;

    double computeSpecialWER(const std::vector<std::vector<unsigned int>> &ref_ids,
                             const std::vector<unsigned int> &hyp_ids, unsigned int nSegments) const;
    unsigned int getVocIndex(const std::string &word) const;
    std::string getVocWord(const unsigned int id) const;

    unsigned int getSubstitutionCosts(const unsigned int a, const unsigned int b) const;
    unsigned int getInsertionCosts(const unsigned int w) const;
    unsigned int additionalInsertionCosts(const unsigned int, const unsigned int, bool, const unsigned int) const;
    unsigned int getDeletionCosts(const unsigned int w) const;
    void fillPunctuationSet();
    bool isInternal(const unsigned int w) const;

  public:
    MwerSegmenter()
        : maxER_(-1), human_(false), ins_(1), del_(1), refLength_(0), vocCounter_(0), usecase(false),
          referencesAreOk(false), segmenting(false)
    {
        fillPunctuationSet();
    }

    ~MwerSegmenter() {}

    void mwerAlign(const std::string &ref, const std::string &hyp, std::string &result);

    /** return normalized number of errors (= error rate)
     * \param sentence hyps Candidate corpus to evaluate
     **/
    double evaluate(const HypContainer &hyps, std::ostream &out = std::cout) const;

    /** write detailed evaluation information to output stream
     * \param out Output stream to write evaluation to
     * \param hyps Candidate corpus to evaluate
     **/
    void detailed_evaluation(std::ostream &, const HypContainer &) const {};

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
    bool loadrefs(const std::string &filename);

    bool loadrefsFromStream(std::istream &in);

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
    typedef std::vector<std::vector<DP>> Matrix;

    void setInsertionCosts(double x) { ins_ = x; }
    void setDeletionCosts(double x) { del_ = x; }
};

inline std::ostream &operator<<(std::ostream &out, const MwerSegmenter::hyptype &x)
{
    std::copy(x.begin(), x.end(), std::ostream_iterator<std::string>(out, " "));
    return out;
};

#endif
