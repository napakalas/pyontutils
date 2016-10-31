#!/usr/bin/env python3.5

# this should be run at NIF-Ontology 93bc1f9643d4ed2c9f14539adb8f3e8bc2df81c5

# TODO need to retrieve the FMA hierarchy...

import os
from collections import defaultdict, namedtuple
import rdflib
from rdflib import URIRef, RDFS, RDF, OWL
import requests
from IPython import embed
from scigraph_client import Vocabulary, Graph
from utils import scigPrint, makeGraph, async_getter, TermColors as tc
from hierarchies import creatTree, flatten

sgg = Graph(cache=True, basePath='http://localhost:9000/scigraph')
sgv = Vocabulary(cache=True, basePath='http://localhost:9000/scigraph')

Query = namedtuple('Query', ['root','relationshipType','direction','depth'])

DBX = 'http://www.geneontology.org/formats/oboInOwl#hasDbXref'  #FIXME also behaves as objectProperty :/
AID =  'http://www.geneontology.org/formats/oboInOwl#hasAlternativeId'
IRBC = 'http://ontology.neuinfo.org/NIF/Backend/BIRNLex_annotation_properties.owl#isReplacedByClass'

PREFIXES = {
    'UBERON':'http://purl.obolibrary.org/obo/UBERON_',
    'NIFGA':'http://ontology.neuinfo.org/NIF/BiomaterialEntities/NIF-GrossAnatomy.owl#',
    'oboInOwl':'http://www.geneontology.org/formats/oboInOwl#',
    'ro':'http://www.obofoundry.org/ro/ro.owl#',
    'replacedBy':'http://purl.obolibrary.org/obo/IAO_0100001',
    'owl':'http://www.w3.org/2002/07/owl#',  # FIXME why is this missing?!

}

nifga_path = os.path.expanduser('~/git/NIF-Ontology/ttl/NIF-GrossAnatomy.ttl')
uberon_path = os.path.expanduser('~/git/NIF-Ontology/ttl/external/uberon.owl')
uberon_bridge_path = 'http://berkeleybop.org/ontologies/uberon/bridge/uberon-bridge-to-nifstd.owl'
#bridge_path = os.path.expanduser('~/git/NIF-Ontology/ttl/uberon-bridge-to-nifstd.ttl')  # scigraph's got us

uberon_obsolete = {'UBERON:0022988',  # obsolete regional part of thalamaus
                   'UBERON:0014606',  # replaced by UBERON:0002434
                  }
# TODO need to unpapck all the oboInOwl:hasAlternativeId entries for the purposes of resolution... (madness)
manual = {'NIFGA:nlx_144456':'UBERON:0034918',  # prefer over UBERON:0002565, see note on UBERON:0034918
          'NIFGA:birnlex_1248':'UBERON:0002434',  # fix for what is surely and outdated bridge
          'NIFGA:nlx_anat_20081242':'UBERON:0004073',  # as of late latest version of uberon 'UBERON:0004073' replaces 'UBERON:0019281'
          'NIFGA:nlx_59721':'UBERON:0001944',  # (equivalentClass NIFGA:nlx_59721 NIFGA:birnlex_703) polutes
          'NIFGA:birnlex_703':'UBERON:0001944',  # insurance
          #'NIFGA:birnlex_1663':'UBERON:0002265',  # FIXME this is in hasDbXref ... AND equivalentClass... wat
          'NIFGA:birnlex_1191':'UBERON:0001885',  # this was already replaced by NIFGA:birnlex_1178, the existing equiv assertion to UBERON:0035560 is also obsolete, so we are overriding so we don't have to chase it all down again

          'NIFGA:birnlex_2598':'UBERON:0000044',  # UBERON:0026602 is the alternative and is a bug from the old version of the uberon to nif bridge :/ this has been fixed in the nifgad branch of the ontology but has not been propagated to scigraph
          'NIFGA:nlx_anat_20090702':'UBERON:0022327',  # UBERON:0032288 is an alternate id for UBERON:0022327
          'NIFGA:birnlex_864':'UBERON:0014450',  # UBERON:0002994 is an alternate id for UBERON:0014450
          'NIFGA:birnlex_2524':'UBERON:0006725',  # UBERON:0028186 is an alternate id for UBERON:0006725

         }

cross_over_issues = 'NIFSUB:nlx_subcell_100205'
wat = 'NIFGA:nlx_144456'


def invert(dict_):
    output = defaultdict(list)
    for k,v in dict_.items():
        output[v].append(k)

    return dict(output)

def review_reps(dict_):
    for k,v in invert(dict_).items():
        if k is None:
            continue
        if len(v) > 1:
            kn = sgv.findById(k)
            print(k, kn['labels'][0])
            for s in kn['synonyms']:
                print(' ' * 4, s)
            for v_ in v:
                n = sgv.findById(v_)
                print(' ' * 8, v_, n['labels'][0])
                for s in n['synonyms']:
                    print(' ' * 12, s)

def review_norep(list_):
    print('List of norep (aka already deprecated) to review')
    for curie in list_:
        n = sgg.getNode(curie)
        scigPrint.pprint_node(n)

def do_deprecation(replaced_by, g, additional_edges):
    ubpref = {'ilx':'http://uri.interlex.org/base/',
              'NLXWIKI':'http://neurolex.org/wiki/'}
    ubpref.update(PREFIXES)
    bridge = makeGraph('uberon-bridge', ubpref)
    graph = makeGraph('NIF-GrossAnatomy', PREFIXES, graph=g)
    #graph.g.namespace_manager._NamespaceManager__cache = {}
    #g.namespace_manager.bind('UBERON','http://purl.obolibrary.org/obo/UBERON_')  # this has to go in again because we reset g FIXME
    udone = set('NOREP')
    uedges = defaultdict(lambda:defaultdict(set))

    def inner(nifga, uberon):

        # check for 'NODEP'
        if uberon == 'NODEP':
            return

        # check neuronames id TODO

        # add replaced by -> uberon
        graph.add_node(nifga, 'replacedBy:', uberon)
        # add deprecated true (ok to do twice...)
        graph.add_node(nifga, OWL.deprecated, True)

        # review nifga relations, specifically has_proper_part, proper_part_of
        # put those relations on the uberon term in the 
        # if there is no uberon term raise an error so we can look into it

        #if uberon not in uedges:
            #uedges[uberon] = defaultdict(set)
        resp = sgg.getNeighbors(nifga)
        edges = resp['edges']
        if nifga in additional_edges:
            edges.append(additional_edges[nifga])
        include = False
        for edge in edges:  # FIXME TODO hierarchy extraction and porting
            #print(edge)
            sub = edge['sub']
            obj = edge['obj']
            pred = edge['pred']
            hier = False
            if pred == 'subClassOf':
                pred = RDFS.subClassOf
                continue
            elif pred == 'equivalentClass':
                pred = OWL.equivalentClass
                continue
            elif pred == 'isDefinedBy':
                pred = RDFS.isDefinedBy
                continue
            elif pred == 'http://www.obofoundry.org/ro/ro.owl#has_proper_part':
                hier = True
                include = True
            elif pred == 'http://www.obofoundry.org/ro/ro.owl#proper_part_of':
                hier = True
                include = True
            elif pred == 'ilx:partOf':
                hier = True
                include = True

            if sub == nifga:
                try:
                    obj = replaced_by[obj]
                except KeyError:
                    print('not in replaced_by', obj)
                if type(obj) == tuple: continue  # TODO
                if hier:
                    if uberon not in uedges[obj][pred]:
                        uedges[obj][pred].add(uberon)
                        bridge.add_hierarchy(obj, pred, uberon)
                else:
                    #bridge.add_node(uberon, pred, obj)
                    pass
            elif obj == nifga:
                try:
                    sub = replaced_by[sub]
                except KeyError:
                    print('not in replaced_by', sub)
                if type(sub) == tuple: continue  # TODO
                if hier:
                    if sub not in uedges[uberon][pred]:
                        uedges[uberon][pred].add(sub)
                        bridge.add_hierarchy(uberon, pred, sub)
                else:
                    #bridge.add_node(sub, pred, uberon)
                    pass

        if uberon not in udone and include:
            try:
                label = sgv.findById(uberon)['labels'][0]
            except IndexError:
                WAT = sgv.findById(uberon)
                embed()
            bridge.add_class(uberon, label=label)
            udone.add(uberon)

    for nifga, uberon in replaced_by.items():
        if type(uberon) == tuple:
            print(uberon)
            for ub in uberon:
                print(ub)
                inner(nifga, ub)
        elif uberon == 'NOREP':
            graph.add_node(nifga, OWL.deprecated, True)  # TODO check for missing edges?
        elif uberon is None:
            continue  # BUT TODAY IS NOT THAT DAY!
        else:
            inner(nifga, uberon)

    return graph, bridge

def print_report(report, fetch=False):
    for eid, r in report.items():
        out = ('**************** Report for {} ****************'
               '\n\tNRID: {NRID}\n\tURID: {URID} {UDEP}\n\tMATCH: {MATCH}\n')
        if not r['MATCH']:
            print(out.format(eid, **r))

        if fetch:
            scigPrint.pprint_node(sgg.getNode('NIFGA:' + eid))
            if r['NRID']: scigPrint.pprint_node(sgg.getNode(r['NRID']))
            if r['URID']: scigPrint.pprint_node(sgg.getNode(r['URID']))

def print_trees(graph, bridge):
    PPO = 'ro:proper_part_of'
    HPP = 'ro:has_proper_part'
    hpp = HPP.replace('ro:', graph.namespaces['ro'])
    ppo = PPO.replace('ro:', graph.namespaces['ro'])
    a, b = creatTree(*Query(tc.red('birnlex_796'), HPP, 'OUTGOING', 10),  # FIXME seems to be a last one wins bug here with birnlex_796 vs NIFGA:birnlex_796 depending on the has seed...
                     json=graph.make_scigraph_json(HPP))
    c, d = creatTree(*Query('NIFGA:birnlex_796', hpp, 'OUTGOING', 10), graph=sgg)
    j = bridge.make_scigraph_json(HPP)  # issue https://github.com/RDFLib/rdflib/pull/661
    e, f = creatTree(*Query('UBERON:0000955', HPP, 'OUTGOING', 10), json=j)
    k_, l_ = creatTree(*Query('NIFGA:nlx_anat_101177', ppo, 'INCOMING', 10), graph=sgg)

    merge = dict(d[-1])  # full tree with ppo converted to hpp
    merge['nodes'].extend(l_[-1]['nodes'])
    merge['edges'].extend([{'sub':e['obj'], 'pred':hpp, 'obj':e['sub']} for e in l_[-1]['edges']])
    m_, n_ = creatTree(*Query('NIFGA:birnlex_796', hpp, 'OUTGOING', 10), json=merge)

    print('nifga dep')
    print(a)
    print('nifga live')
    print(c)
    print('new bridge')
    print(e)
    print('nifga total (both directions)')
    print(m_)

    print('nifga white matter')
    print(k_)

    return a, b, c, d, e, f, k_, l_, m_, n_

def new_replaced_by(ids, existing):
    out = {}
    for k in ids:
        if k in existing:
            out[k] = existing[k]
        else:
            out[k] = None
    return out

def make_uberon_graph():
    #ub = rdflib.Graph()
    #ub.parse(uberon_path)  # LOL rdflib your parser is slow
    SANITY = rdflib.Graph()
    #ont = requests.get(uberon_bridge_path).text
    with open('/home/tom/files/onts/uberon-bridge-to-nifstd.owl', 'rt') as f: ont = f.read()  # temp fix during internet out version does not match
    split_on = 263
    #with open('/mnt/tstr/downloads/monarch/uberon-bridge-to-nifstd.owl', 'rt') as f: ont = f.read()  # temp fix during internet out version does not match
    #split_on = 362

    prefs = ('xmlns:NIFSTD="http://uri.neuinfo.org/nif/nifstd/"\n'
             'xmlns:UBERON="http://purl.obolibrary.org/obo/UBERON_"\n')
    ont = ont[:split_on] + prefs + ont[split_on:]
    SANITY.parse(data=ont)
    u_replaced_by = {}
    for s, o in SANITY.subject_objects(OWL.equivalentClass):
        nif = SANITY.namespace_manager.qname(o)
        uberon = SANITY.namespace_manager.qname(s)
        if nif in u_replaced_by:
            one = u_replaced_by[nif]
            u_replaced_by[nif] = one, uberon
            print('WE GOT DUPES', nif, one, uberon)  # TODO

        u_replaced_by[nif] = uberon
        #print(s, o)
        #print(nif, uberon)

    return u_replaced_by

def make_neurolex_graph():
    # neurolex test stuff
    nlxpref = {'ilx':'http://uri.interlex.org/base/'}
    nlxpref.update(PREFIXES)
    neurolex = makeGraph('neurolex-temp', nlxpref)
    neurolex.g.parse('/tmp/neurolex_basic.ttl', format='turtle')

    ILXPO = 'ilx:partOf'
    nj = neurolex.make_scigraph_json(ILXPO)
    g_, h = creatTree(*Query('NIFGA:birnlex_796', ILXPO, 'INCOMING', 10), json=nj)
    i_, j_ = creatTree(*Query('NIFGA:nlx_412', ILXPO, 'INCOMING', 10), json=nj)

    brht = sorted(set(flatten(h[0],[])))
    wmht = sorted(set(flatten(j_[0],[])))
    ufixedrb = {'NIFGA:' + k.split(':')[1]:v for k, v in u_replaced_by.items()}
    b_nlx_replaced_by = new_replaced_by(brht, ufixedrb)
    w_nlx_replaced_by = new_replaced_by(wmht, ufixedrb)
    additional_edges = defaultdict(list)  # TODO this could be fun for the future but is a nightmare atm
    for edge in h[-1]['edges'] + j_[-1]['edges']:
        additional_edges[edge['sub']] = edge
        additional_edges[edge['obj']] = edge

    #filter out bad edges becase we are lazy
    additional_edges = {k:v for k, v in additional_edges.items()
                        if k in b_nlx_replaced_by or k in w_nlx_replaced_by}

    print('neurolex tree')  # computed above
    print(g_)
    print(i_)

    return additional_edges

def do_report(nif_bridge, ub_bridge):
    report = {}
    for existing_id, nif_uberon_id in nif_bridge.items():
        cr = {}
        cr['UDEP'] = ''
        if nif_uberon_id == 'NOREP':
            cr['NRID'] = ''
        elif nif_uberon_id == 'NODEP':
            cr['NRID'] = ''
        else:
            cr['NRID'] = nif_uberon_id

        if existing_id in ub_bridge:
            ub_uberon_id = ub_bridge[existing_id]
            cr['URID'] = ub_uberon_id
            if type(nif_uberon_id) == tuple:
                if ub_uberon_id in nif_uberon_id:
                    match = True
                else:
                    match = False
            elif ub_uberon_id != nif_uberon_id:
                match = False
            else:
                match = True

        else:
            match = False
            cr['URID'] = ''
            if cr['NRID']:
                meta = sgg.getNode(nif_uberon_id)['nodes'][0]['meta']
                if 'http://www.w3.org/2002/07/owl#deprecated' in meta and meta['http://www.w3.org/2002/07/owl#deprecated']:
                    cr['UDEP'] = 'Deprecated'

        cr['MATCH'] = match
        report[existing_id] = cr

    return report

def make_nifga_graph():
    # use equivalent class mappings to build a replacement mapping
    g = rdflib.Graph()
    g.parse(nifga_path, format='turtle')

    getQname = g.namespace_manager.qname
    classes = sorted([getQname(_) for _ in g.subjects(RDF.type, OWL.Class) if type(_) is URIRef])
    curies = ['NIFGA:' + n for n in classes if ':' not in n]
    matches = async_getter(sgv.findById, [(c,) for c in curies])
    #tests = [n for n,t in zip(curies, matches) if not t]  # passed

    replaced_by = {}
    exact = {}
    internal_equivs = {}
    #edges = [e for e in sgg.getEdges(DBX, limit=999999)['edges'] if e['obj'].startswith(':')]
    def equiv(curie, label):
        if curie in manual:
            replaced_by[curie] = manual[curie]
            return manual[curie]

        ec = sgg.getNeighbors(curie, relationshipType='equivalentClass')
        nodes = [n for n in ec['nodes'] if n['id'] != curie]
        if len(nodes) > 1:
            #print('wtf node', [n['id'] for n in nodes], curie)
            for node in nodes:
                id_ = node['id']
                label_ = node['lbl']

                if id_.startswith('UBERON'):
                    if curie in replaced_by:
                        one = replaced_by[curie]
                        replaced_by[curie] = one, id_
                        print('WE GOT DUPES', curie, label, one, id_)  # TODO
                    else:
                        replaced_by[curie] = id_
                else:
                    internal_equivs[curie] = id_
        elif not nodes:
            # check if uberon has a xref edge that matches...
            # seems like we already hit this in some other ways
            #for e in edges:
                #print(e, curie)
                #if curie == 'NIFGA' + e['obj']:
                    #print()
                    #print('CANDIDATE EDGE REPLACE:')
                    #print(e)
                    #print()
                    #break
            # otherwise we go hunting
            node = sgg.getNode(curie)['nodes'][0]
            if OWL.deprecated.toPython() in node['meta']:
                print('THIS CLASS IS DEPRECATED', curie)
                if IRBC in node['meta']:
                    existing_replaced = node['meta'][IRBC][0]
                    ec2 = sgg.getNeighbors(existing_replaced, relationshipType='equivalentClass')
                    print('FOUND ONE', existing_replaced)
                    scigPrint.pprint_node(sgg.getNode(existing_replaced))
                    if ec2['edges']:  # pass the buck if we can
                        scigPrint.pprint_edge(ec2['edges'][0])
                        rb = ec2['edges'][0]['obj']
                        print('PASSING BUCK : (%s -> %s -> %s)' % (curie, existing_replaced, rb))
                        replaced_by[curie] = rb
                    else:
                        print('ERROR: could not pass buck, we are at a dead end')  # TODO
                    print()

            moar = [t for t in sgv.findByTerm(label) if t['curie'].startswith('UBERON')]
            if moar:
                #print(moar)
                #replaced_by[curie] = moar[0]['curie']
                if len(moar) > 1:
                    print('WARNING', curie, label, [(m['curie'], m['labels'][0]) for m in moar])

                for node in moar:
                    if node['curie'] in uberon_obsolete:  # node['deprecated']?
                        continue
                    ns = sgg.getNode(node['curie'])
                    assert len(ns['nodes']) == 1, "WTF IS GOING ON %s" % node['curie']
                    ns = ns['nodes'][0]
                    if DBX in ns['meta']:
                        print(' ' * 8, node['curie'], ns['meta'][DBX],
                              node['labels'][0], node['synonyms'])

                    if AID in ns['meta']:
                        print(' ' * 8, node['curie'], ns['meta'][AID],
                              node['labels'][0], node['synonyms'])

                    #else:
                        #print(' ' * 8, 'NO DBXREF', node['curie'],
                              #node['labels'][0], node['synonyms'])
                        #pass  # these are all to obsolote uberon classes
                    replaced_by[curie] = ns['id']
            else:
                replaced_by[curie] = None
                if False:  # review
                    print('NO FORWARD EQUIV', tc.red(curie), label)  # TODO
                    for k,v in sorted(sgg.getNode(curie)['nodes'][0]['meta'].items()):
                        if type(v) == iter:
                            print(' ' * 4, k)
                            for _ in v:
                                print(' ' * 8, _)
                        else:
                            print(' ' * 4, k, v)
        else:
            node = nodes[0]
            replaced_by[curie] = node['id']
            exact[curie] = node['id']

        return nodes

    #equivs = async_getter(equiv, [(c['curie'], c['labels'][0]) for c in matches if not c['deprecated']])
    #equivs = async_getter(equiv, [(c['curie'], c['labels'][0]) for c in matches])  # give the deped a shot!
    equivs = [equiv(c['curie'], c['labels'][0]) for c in matches]  # async causes print issues :/

    return g, matches, exact, internal_equivs, replaced_by

def main():
    u_replaced_by = make_uberon_graph()
    additional_edges = make_uberon_graph()
    g, matches, exact, internal_equivs, replaced_by = make_nifga_graph()

    #review_norep([m['curie'] for m in matches if m['deprecated']])
    #review_reps(exact)  # these all look good
    #review_reps(replaced_by)  # as do these

    #rpob = [_['id'] for _ in sgg.getNeighbors('NIFGA:birnlex_1167', relationshipType='subClassOf')['nodes'] if 'UBERON:' not in _['id']]  # these hit pretty much everything because of how the subclassing worked out, so can't use this
    regional_no_replace = {k:v for k,v in replaced_by.items() if not v and sgv.findById(k)['labels'][0].startswith('Regional')}
    for k in regional_no_replace:
        replaced_by[k] = 'NODEP'  # do not deprecated these for the time being
   
    graph, bridge = do_deprecation(replaced_by, g, {})  # additional_edges)  # TODO
    bridge.write()
    graph.write()

    trees = print_trees(graph, bridge)

    # we do this because each of these have different prefixes :(
    nif_bridge = {k.split(':')[1]:v for k, v in replaced_by.items()}  # some are still None
    ub_bridge = {k.split(':')[1]:v for k, v in u_replaced_by.items()}

    report = do_report(nif_bridge, ub_bridge)

    double_checked = {i:r for i, r in report.items() if r['MATCH']}  # aka exact from above
    no_match = {i:r for i, r in report.items() if not r['MATCH']}
    no_replacement = {i:r for i, r in report.items() if not r['NRID']}
    very_bad = {i:r for i, r in report.items() if not r['MATCH'] and r['URID'] and not r['UDEP']}

    fetch = False
    print('\n>>>>>>>>>>>>>>>>>>>>>> No match reports\n')
    #print_report(no_match, fetch)
    print('\n>>>>>>>>>>>>>>>>>>>>>> No replace reports\n')
    #print_report(no_replacement, fetch)
    print('\n>>>>>>>>>>>>>>>>>>>>>> No match and not deprecated reports\n')
    print_report(very_bad, fetch)

    print('Match count', len(double_checked))
    print('No Match count', len(no_match))
    print('No replace count', len(no_replacement))  # there are none with a URID and no NRID
    print('No match not deprecated count', len(very_bad))

    embed()





if __name__ == '__main__':
    main()
