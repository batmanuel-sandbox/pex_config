/**
 * @file Policy_1.cc
 *
 * This test tests the basic access and update methods of the Policy class.
 */
#include <iostream>
#include <sstream>
#include <string>
#include <stdexcept>
#include "lsst/mwi/policy/Policy.h"
#include "lsst/mwi/policy/PolicyFile.h"

using namespace std;
using lsst::mwi::policy::Policy;
using lsst::mwi::policy::PolicyFile;
using lsst::mwi::policy::TypeError;
using lsst::mwi::policy::NameNotFound;

#define Assert(b, m) tattle(b, m, __LINE__)

void tattle(bool mustBeTrue, const string& failureMsg, int line) {
    if (! mustBeTrue) {
        ostringstream msg;
        msg << __FILE__ << ':' << line << ":\n" << failureMsg << ends;
        throw runtime_error(msg.str());
    }
}

int main() {

    Policy p;

    // tests on an empty policy
    Assert(! p.exists("foo"), "empty existence test failed");
    Assert(p.valueCount("foo.bar") == 0, "empty valueCount test failed");
    Assert(! p.isInt("foo"), "empty existence type test failed");

    try {  p.getTypeInfo("foo"); }
    catch (NameNotFound&) { }

    Assert(p.getInt("foo", 5) == 5, "providing default failed");

    p.set("doall", "true");

    // non-existence tests on a non-empty policy
    Assert(! p.exists("foo"), "non-empty non-existence test failed");
    Assert(p.valueCount("foo.bar") == 0, "empty valueCount test failed");
    Assert(! p.isInt("foo"), "non-empty non-existence type test failed");

    try {  p.getTypeInfo("foo"); }
    catch (NameNotFound& e) { 
        cout << "foo confirmed not to exist: " << e.what() << endl;
    }

    // existance tests
    Assert(p.exists("doall"), "non-empty existance test failed");
    Assert(p.valueCount("doall") == 1, "single valueCount test failed");

    // test out our newly added parameter
    try {  p.getInt("doall"); }
    catch (TypeError& e) { 
        cout << "doall confirmed not an Int: " << e.what() << endl;
    }
    try {  p.getDoubleArray("doall"); }
    catch (TypeError&) { }

    cout << "doall: " << p.getString("doall") << endl;
    Assert(p.getString("doall") == "true", "top-level getString failed");
    p.set("doall", "duh");
    cout << "doall: " << p.getString("doall") << endl;
    Assert(p.getString("doall") == "duh", "top-level reset failed");

    // test that we can access this property as an array
    vector<Policy::StringPtr> ary = p.getStringArray("doall");
    Assert(ary.size() == 1, "scalar property has more than one value");
    Assert(*(ary[0]) == "duh", "scalar access via array failed");

    p.add("doall", "never");
    cout << "doall: " << p.getString("doall") << endl;

    Assert(p.valueCount("doall") == 2, "2-elem. valueCount test failed");

    // make sure that we can access an array as a scalar properly
    Assert(p.getString("doall") == "never", "top-level add failed");

    // test array access
    ary = p.getStringArray("doall");
    cout << "doall (" << ary.size() << "):";
    for(vector<Policy::StringPtr>::iterator pi=ary.begin();pi!=ary.end();++pi) 
        cout << ' ' << **pi;
    cout << endl;
    Assert(ary.size() == 2, "scalar property has wrong number of values");
    Assert(*(ary[0]) == "duh", "scalar access via (2-el) array failed");
    Assert(*(ary.back()) == "never", "scalar access via (2-el) array failed");

    // test PolicyFile type
    string pfile("test.paf");
    p.add("test", Policy::FilePtr(new PolicyFile(pfile)));
    Assert(p.getValueType("test") == Policy::FILE, 
           "Wrong ValueType for PolicyFile");
    Assert(p.isFile("test"), "PolicyFile's type not recognized");
    Policy::FilePtr pf = p.getFile("test");
    Assert(pf->getPath() == pfile, "Corrupted PolicyFile name");
        
    // test hierarchical access
    string standalone("Dictionary.definition.standalone");
    string minOccurs = standalone+".minOccurs";
    p.set(minOccurs, 1);
    cout << minOccurs << ": " << p.getInt(minOccurs) << endl;
    Assert(p.getInt(minOccurs) == 1, "hierarchical property set failed");
    Assert(p.exists(minOccurs), "hierarchical existence test failed");
    Assert(p.valueCount(minOccurs) == 1,"hierarchical valueCount test failed");

    Policy::Ptr sp = p.getPolicy(standalone);
    sp->set("type", "int");
    cout <<  standalone+".type"<< ": " << p.getString(standalone+".type") 
         << endl;
    Assert(p.getString(standalone+".type") == "int", "encapsulated set failed");
    sp->set("required", false);
    cout << standalone+".required"<< ": " << p.getBool(standalone+".required") 
         << endl;
    Assert(!p.getBool(standalone+".required"), "boolean set failed");

    sp->add("score", 3.4);
    cout <<  standalone+".score"<< ": " << p.getDouble(standalone+".score") 
         << endl;
    Assert(sp->getDouble("score") - 3.4 < 0.0000000000001, 
           "double type set failed");

    // list names
    list<string> names;
    int npol = p.policyNames(names);
    int nprm = p.paramNames(names);
    int nfile = p.fileNames(names);
    int nall = p.names(names);
    cout << "policy now has " << nall << " names (" << npol << " policies, "
         << nprm << " parameters):" << endl;
    for(list<string>::iterator i=names.begin(); i!=names.end(); ++i) 
        cout << "   " << *i << ": " << p.getTypeName(*i) << endl;
    Assert(npol + nfile + nprm == nall, "name listing failed");

    // show Types
    cout << "Types:" << endl;
    cout << "\tdoall: " << p.getTypeInfo("doall").name() << endl;
    cout << "\tminOccurs: " << sp->getTypeInfo("minOccurs").name() << endl;
    cout << "\tscore: " << sp->getTypeInfo("score").name() << endl;
    cout << "\trequired: " << sp->getTypeInfo("required").name() << endl;
    cout << "\tstandalone: " 
         << p.getTypeInfo("Dictionary.definition.standalone").name() << endl;
    cout << "\ttest: " << p.getTypeInfo("test").name() << endl;

    // Test shallow and deep copies
    Policy shallow(p);
    sp->add("score", 1.355);
    Assert(shallow.getDouble(standalone + ".score") - 1.355 < 0.000000001,
           "shallow copy failure");

    Policy deep(p);
    sp->add("score", 1.355);
    Assert(shallow.getDouble(standalone + ".score") - 3.4 < 0.000000001,
           "shallow copy failure");
}