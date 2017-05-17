#!/usr/bin/env python3.6

import os
import json
from glob import glob
from hashlib import md5
from functools import wraps
import rdflib
from pyontutils.utils import makePrefixes, makeGraph

# ilx api implementation (will change)
import csv
import requests
from io import StringIO

#debug
from IPython import embed

# interlex api (temp version)
ILX_ENDPOINT = 'https://test.scicrunch.org/forms/term-forms/term-bulk-upload.php'
CID = 72  # SciCrunch community id
ilx_session = requests.Session()
ILX_USER, ILX_PASS = os.environ.get('ILX_USER'), os.environ.get('ILX_PASS')
ilx_session.auth = (ILX_USER, ILX_PASS)  # basic auth but fails?
def getNewIlxId(temp_id, seed, ontid):
    # Label[tab] Type[tab] Definition[tab] OntologyURLs[tab] Comment[tab] Synonym::Type[tab] Curie::Iri::Preferred[tab] Superclasses[new line]
    row = 'TOM TEST TERM', 'term', None, ontid, temp_id, None, None, None
    sio = StringIO()
    writer = csv.writer(sio, lineterminator='\n', delimiter='\t')
    writer.writerow(row)
    data = {'file':sio, 'cid':CID}
    req = requests.Request(method='POST', url=ILX_ENDPOINT, data=data)
    req.headers
    prep = req.prepare()
    resp = ilx_session.send(prep, verify=False)
    embed()
    #return 'ILX:1234567'

# file handling

__FILENAME = os.path.join(os.path.dirname(__file__), 'resources/nif-ilx-replace.json')

def setfilename(filepath):
    if not os.path.exists(filepath):
        dn = os.path.dirname(filepath)
        if dn and not os.path.exists(dn):
            os.mkdir(dn)  # hack for creating resources inside site-packages which will likely fail with permissions errors if --user was not installed by pip :/
        with open(filepath, 'wt') as f:
            f.write('{}\n')
    global __FILENAME
    __FILENAME = filepath

# check temp_id status

setfilename(__FILENAME)

def managed(mode='rt+'):
    func = None
    if callable(mode):
        func = mode
        mode = 'rt+'
    def managed_(function):
        function.__globals__['FIRST'] = True
        @wraps(function)
        def inner(*args, TEMP_INDEX=None, **kwargs):
            print(__FILENAME)
            with open(__FILENAME, mode) as f:  # + maintains a lock
                if TEMP_INDEX is None:
                    TEMP_INDEX = json.load(f)
                    f.seek(0)
                output = function(*args, TEMP_INDEX=TEMP_INDEX, **kwargs)
                if f.writable():
                    json.dump(TEMP_INDEX, f, sort_keys=True, indent=4)
            return output
        return inner
    if func is not None:
        return managed_(func)
    else:
        return managed_

class RecMan:
    """ A completely unsafe way to read and write
        python dicts to json on disk """
    def __init__(self, recfilepath):
        self._check_exists_or_create(recfilepath)
        self.filepath = recfilepath
        self._file = None
        self.DATA = {}

    def write(self):
        with open(self.filepath, 'wt') as f:
            json.dump(self.DATA, f, sort_keys=True, indent=4)

    def read(self):
        with open(self.filepath, 'rt') as f:
            self.DATA = json.load(f)

def makeIlxRec(label,
               definition='',
               type='term',
               comment='',
               synonyms=tuple(),
               existing_ids=tuple(),
               superclass=None,
               ontologies=tuple()):
        out = {'label':label,
               'definition':definition,
               'type':str(type),
               'comment':str(comment),
               'synonyms':[{'literal':str(s), 'type':''} for s in synonyms],
               'existing_ids':[{'curie':c, 'iri':'', 'preferred':'0'} for c in existing_ids],
               'superclass':{'label':superclass}, 'ontologies':[{'url':str(u)} for u in ontologies]}
        return out



@managed
def ilxGetRealId(temp_id, ontid, TEMP_INDEX=None):
    # NOTE run on files after creation, ontid doesn't always exist before
    if temp_id not in TEMP_INDEX:
        print('temp_id %s found that is not in %s where did it come from?' % (temp_id, __FILENAME))
        ilxLookupOrAdd(temp_id, TEMP_INDEX=TEMP_INDEX)
    record = TEMP_INDEX[temp_id]
    if not record['ilx']:
        record['ontid'] = ontid
        real_id = getNewIlxId(temp_id, ontid)
        record['ilx'] = real_id

@managed
def ilxAddTempId(temp_id, ontid=None, TEMP_INDEX=None):  # FIXME simplify
    if temp_id in TEMP_INDEX:
        record = TEMP_INDEX[temp_id]
        if record['ilx']:
            return record['ilx']  # return the real identifier
        elif ontid and not record['ontid']:
            record['ontid'] = ontid
    else:
        TEMP_INDEX[temp_id] = {'ilx':None, 'ontid':ontid}

    return temp_id

@managed
def ilxLookupExisting(temp_id, TEMP_INDEX=None):
    return TEMP_INDEX[temp_id]  # KeyError ok here

def ILXREPLACE(seed):
    h = md5()
    h.update(seed.encode())
    temp_id = 'ILXREPLACE:' + h.hexdigest()
    try:
        e = ilxLookupExisting(temp_id)
        if e is not None:
            return e
        else:
            print(temp_id, 'has been read from a file but has not been replaced.')
    except KeyError:
        pass

    return temp_id

def readFile(filename, existing):
    graph = rdflib.Graph()
    graph.parse(filename, format='turtle')
    fn = os.path.splitext(filename)[0]
    print(fn)
    mg = makeGraph(fn, prefixes=makePrefixes('OBOANN'), graph=graph, writeloc='')
    if 'ILXREPLACE' in mg.namespaces:
        namespace = str(mg.namespaces['ILXREPLACE'])
    else:
        print('Nothing needs to be replaced in', filename)
        return 
    query = ("SELECT DISTINCT ?v "
             "WHERE { {?v ?p ?o} UNION {?s ?v ?o} UNION {?s ?p ?v} . "
             "FILTER("
             "strstarts(str(?v), '%s') )}") % namespace
    vals = graph.query(query)
    #existing = {}  # TODO this needs to populate from an existing source ie the ontology, and a tempid -> realid map?
    for val, in vals:
        qn = graph.namespace_manager.qname(val)
        try:
            labs = list(graph.objects(val, rdflib.RDFS.label))
            print(labs)
            label = str(labs[0])
        except IndexError:
            label = None
            pass  # not defined here but we need to collect info here anyway
            #continue  # this id is not defined here, but we probably will want to replace it
        definition = list(graph.objects(val, rdflib.namespace.SKOS.definition))
        if definition: definition = definition[0]
        s = mg.expand('OBOANN:synonym')
        synonyms = list(graph.objects(val, s))
        superclass = list(graph.objects(val, rdflib.RDFS.subClassOf))
        superclass = superclass[0] if superclass else None
        rec = makeIlxRec(label, definition, type='term', comment=qn, synonyms=synonyms, existing_ids=[], superclass=superclass, ontologies=[mg.ontid])
        print(rec)
        #ilxAddTempId(qn, ontid=mg.ontid)
        if qn in existing:
            existing[qn]['files'].append(filename)
            newrec = {}
            for k, v in existing[qn]['rec'].items():
                if v:
                    newrec[k] = v
                else:
                    newrec[k] = rec[k]
            existing[qn]['rec'] = newrec

        else:
            existing[qn] = {'id':None, 'files':[filename], 'rec':rec}
            print('NEW')
        print(qn, mg.ontid)
        #ilxGetRealId(qn, mg.ontid)

    # TODO warn on existing entry

    #ilxDoReplace(mg)

def replaceFile(filename):
    readFile(filename)
    
@managed('rt')
def ilxDoReplace(mg, TEMP_INDEX=None):
    mg.add_namespace('ILX', makePrefixes('ILX')['ILX'])
    mg.del_namespace('ILXREPLACE')
    for temp_id, record in TEMP_INDEX.items():
        if not record['ilx']:
            print('%s is missing a real ilx id. Please make sure you have run ilxGetRealId on all entires for %s' % (temp_id, mg.ontid))
        mg.replace_uriref(temp_id, record['ilx'])
    mg.write()

    if ilxDoReplace.__globals__['FIRST']:
        ilxDoReplace.__globals__['FIRST'] = False
        #embed()

def ilx_json_to_tripples(j):  # this will be much eaiser if everything can be exported as a relationship or an anotation
    g = makeGraph('do not write me', prefixes=makePrefixes('ILX', 'ilx', 'owl', 'skos', 'OBOANN'))
    def pref(inp): return makePrefixes('ilx')['ilx'] + inp
    id_ =  pref(j['ilx'])
    type_ = {'term':'owl:Class','relationship':'owl:ObjectProperty','annotation':'owl:AnnotationProperty'}[j['type']]
    out = []  # TODO need to expand these
    out.append( (id_, rdflib.RDF.type, type_) )
    out.append( (id_, rdflib.RDFS.label, j['label']) )
    out.append( (id_, 'skos:definition', j['definition']) )
    for syndict in j['synonyms']:
        out.append( (id_, 'OBOANN:synonym', syndict['literal']) )
    for superdict in j['superclasses']:  # should we be returning the preferred id here not the ilx? or maybe that is a different json output?
        out.append( (id_, rdflib.RDFS.subClassOf, pref(superdict['ilx'])) )
    for eid in j['existing_ids']:
        out.append( (id_, 'ilx:someOtherId', eid['iri']) )  # predicate TODO
    [g.add_node(*o) for o in out]
    return g.g.serialize(format='nifttl')  # other formats can be choosen

def main():
    #with open('ilxjson.json', 'rt') as f:
        #a = ilx_json_to_tripples(json.load(f))
        #print(a.decode())
    #return
    if not os.path.exists(__FILENAME):
        with open(__FILENAME, 'wt') as f:
            json.dump({}, f)

    ILXREPLACE('wowzers')
    ILXREPLACE('are you joking')
    ilxGetRealId(ILXREPLACE('wowzers'), 'http://FIXME.org/thing.ttl')
    #return
    for file in glob('/home/tom/git/NIF-Ontology/ttl/generated/parcellation/*.ttl'):
        ilxGet(file)
    ilxGet('/home/tom/git/NIF-Ontology/ttl/generated/parcellation.ttl')

if __name__ == '__main__':
    main()
