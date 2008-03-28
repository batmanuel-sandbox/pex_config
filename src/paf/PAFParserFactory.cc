/**
 * @class PAFParserFactory
 * 
 * @ingroup mwi
 *
 * @author Ray Plante
 * 
 */

#include "lsst/mwi/policy/paf/PAFParserFactory.h"
#include "lsst/mwi/policy/paf/PAFParser.h"

namespace lsst {
namespace mwi {
namespace policy {
namespace paf {

using boost::regex_search;

/** 
 * a name for the format
 */
const string PAFParserFactory::FORMAT_NAME("PAF");

const regex PAFParserFactory::LEADER_PATTERN("^\\s*\\w");
const regex 
     PAFParserFactory::CONTENTID("^\\s*#\\s*<\\?cfg\\s+PAF(\\s+\\w+)*\\s*\\?>",
                                regex::icase);

/**
 * create a new PolicyParser class and return a pointer to it.  The 
 * caller is responsible for destroying the pointer.
 * @param  policy   the Policy object that data should be loaded into.
 */
PolicyParser* PAFParserFactory::createParser(Policy& policy, 
                                             bool strict) const 
{ 
    return new PAFParser(policy, strict);
}

/**
 * return the name for the format supported by the parser
 */
const string& PAFParserFactory::getFormatName() { return FORMAT_NAME; }

/**
 * analyze the given string assuming contains the leading characters 
 * from the data stream and return true if it is recognized as being in 
 * the format supported by this parser.  If it is, return the name of 
 * the this format; 
 */
bool PAFParserFactory::recognize(const string& leaders) const { 
    return (regex_search(leaders, contentid) || 
            regex_search(leaders, LEADER_PATTERN));
}




}}}}   // end lsst::mwi::policy::paf