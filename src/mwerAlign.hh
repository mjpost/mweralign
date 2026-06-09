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

    /** A single recorded Levenshtein cell from the segmentation DP.
     *
     * Only populated when trace collection is enabled (see setCollectTrace()).
     * Lets callers inspect, per hypothesis/reference position, the competing
     * edit costs the DP considered and which one (and what penalty) it chose.
     **/
    struct CellCost {
        unsigned int j;        ///< hypothesis position (1-based)
        unsigned int i;        ///< reference position  (1-based)
        unsigned int ref;      ///< reference index
        unsigned int del_cost; ///< total cost of the deletion option
        unsigned int ins_cost; ///< total cost of the insertion option
        unsigned int sub_cost; ///< total cost of the substitution option
        unsigned int chosen;   ///< cost of the option the DP took
        unsigned int extra;    ///< segment-initial internal-word penalty applied here
        char op;               ///< chosen edit: 'S', 'I' or 'D'
        bool is_new_sent;      ///< whether this cell is at a segment start
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
    // TEMPORARY: when true, restore the pre-fix (paper) behavior where the
    // segment-initial "internal word" penalty fires regardless of the
    // segmenting flag. Used to reproduce results produced before the
    // untokenized-alignment fix. See setLegacyPenalty().
    bool legacyPenalty_;

    const std::string underscoreWord = "▁";

    /** Container for the reference sentences **/
    MRefContainer mref;
    mutable std::map<std::string, unsigned int> vocMap_;
    mutable std::map<unsigned int, std::string> voc_id_to_word_map_;

    mutable std::set<unsigned int> punctuationSet_;
    mutable std::vector<unsigned int> boundary;
    mutable std::vector<unsigned int> sentCosts;

    // --- Optional alignment trace (opt-in; zero overhead when disabled) ---
    // When collectTrace_ is false the DP touches none of the storage below and
    // pays only a single (statically predicted-not-taken) branch per cell.
    // Boundary tables are O(J*S) and cheap; per-cell costs are O(J*I*R) and are
    // gated behind the separate collectCells_ flag so the boundary trace stays
    // usable on real (long) inputs.
    mutable bool collectTrace_ = false;
    mutable bool collectCells_ = false;
    mutable std::vector<std::vector<unsigned int>> traceBC_; ///< BC[j][s]: best cost ending segment s at hyp pos j
    mutable std::vector<std::vector<unsigned int>> traceBP_; ///< BP[j][s]: backpointer (end of segment s-1)
    mutable std::vector<std::vector<unsigned int>> traceBR_; ///< BR[j][s]: best reference index
    mutable std::vector<CellCost> traceCells_;               ///< per-cell edit costs (large; debug-only)

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
          referencesAreOk(false), segmenting(false), legacyPenalty_(false)
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

    /** TEMPORARY: restore the pre-fix penalty behavior.
     * When enabled, the segment-initial "internal word" penalty is applied even
     * for untokenized (whitespace) input, reproducing results generated before
     * the alignment fix. Off by default.
     * \param b \em true: apply the penalty unconditionally (legacy/paper behavior)
     **/
    void setLegacyPenalty(bool b) { legacyPenalty_ = b; }

    /** Enable or disable collection of the alignment trace.
     *
     * When enabled, the next call to evaluate()/mwerAlign() records the full
     * boundary DP table (cost, backpointer and best reference for every
     * candidate segment end) and every Levenshtein cell's competing costs.
     * Disabled by default; when disabled the DP pays no measurable cost.
     * \param b \em true: collect the trace; \em false: do not (default)
     **/
    void setCollectTrace(bool b) { collectTrace_ = b; }

    /** \return whether trace collection is currently enabled **/
    bool collectTrace() const { return collectTrace_; }

    /** Enable or disable per-cell cost recording.
     *
     * Per-cell costs are O(J*I*R) and only meaningful for small/diagnostic
     * inputs; the boundary tables (O(J*S)) are recorded whenever
     * setCollectTrace(true) is set, independent of this flag. Disabled by
     * default.
     * \param b \em true: also record every Levenshtein cell's costs
     **/
    void setCollectCells(bool b) { collectCells_ = b; }

    /** \return whether per-cell cost recording is currently enabled **/
    bool collectCells() const { return collectCells_; }

    /** Boundary cost table from the last traced alignment: BC[j][s] is the best
     * total cost of a segmentation that ends segment \c s at hypothesis
     * position \c j. Empty unless setCollectTrace(true) was set. **/
    const std::vector<std::vector<unsigned int>> &traceBoundaryCost() const { return traceBC_; }

    /** Boundary backpointer table: BP[j][s] is the hypothesis position at which
     * segment \c s-1 ends in the best segmentation ending segment \c s at \c j. **/
    const std::vector<std::vector<unsigned int>> &traceBoundaryBP() const { return traceBP_; }

    /** Best-reference table: BR[j][s] is the reference index chosen for the
     * segment ending at \c j with segment count \c s. **/
    const std::vector<std::vector<unsigned int>> &traceBoundaryRef() const { return traceBR_; }

    /** Per-cell edit costs recorded during the last traced alignment. **/
    const std::vector<CellCost> &traceCells() const { return traceCells_; }

    /** Chosen segment boundaries from the last alignment: boundary[s] is the
     * hypothesis position at which segment \c s-1 ends. **/
    const std::vector<unsigned int> &boundaries() const { return boundary; }

    /** Cumulative segment costs from the last alignment. **/
    const std::vector<unsigned int> &segmentCosts() const { return sentCosts; }

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
