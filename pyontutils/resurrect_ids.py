#!/usr/bin/env python3.6
"""Extract alternative ids from an ontology and make them owl:Classes again

Usage:
    resurect_ids [options] <file>...

Options:
    -h --help       print this
    -v --verbose    do something fun!
    -s --slow       do not use a process pool
    -n --nowrite    parse the file and reserialize it but do not write changes

"""

import os
from docopt import docopt
import rdflib
from pyontutils.utils import makePrefixes, makeGraph, createOntology, anyMembers
from IPython import embed

args = docopt(__doc__, version = "resurect-ids 0")

def kludge(filepath):
    if 'doid' in filepath:
        return 'DOID',
    elif 'uberon' in filepath:
        return 'UBERON',
    elif 'go' in filepath:
        return 'GO',
    elif 'pr' in filepath:
        return 'PR',
    elif 'ero' in filepath:
        return 'ERO',
    elif 'pato' in filepath:
        return 'PATO',
    else:
        raise NameError('We don\' know what to do with identifers from %s' % filepath)

def alreadyHasEntry(oldClassString, og):
    """ Return true if there is already an owl:Class with the old id"""
    namespace = oldClassString.split(':')[0]
    if namespace == 'http':
        target = rdflib.URIRef(oldClassString)
        print('OLD CLASS ID IS A URL', oldClassString)
    else:
        try:
            og.add_known_namespace(namespace)
            target = og.expand(oldClassString)
        except KeyError:
            print('MISSING NAMESPACE', namespace, oldClassString)
            return True  # we only want known namespaces
    return (target, rdflib.RDF.type, rdflib.OWL.Class) in og.g

def extract(file):
    filepath = os.path.expanduser(file)
    _, ext = os.path.splitext(filepath)
    filetype = ext.strip('.')
    if filetype == 'ttl':
        infmt = 'turtle'
    else:
        infmt = None
    print(filepath)
    graph = rdflib.Graph()
    try:
        graph.parse(filepath, format=infmt)
    except rdflib.plugins.parsers.notation3.BadSyntax as e:
        print('PARSING FAILED', filepath)
        raise e
    og = makeGraph('', graph=graph)

    # FIXME this should really just be a function :/
    curie, *prefs = kludge(filepath)

    name = os.path.splitext(os.path.basename(filepath))[0]
    version = list(graph.subject_objects(rdflib.OWL.versionIRI))[0][1]

    ng = createOntology(f'{name}-dead',
                        f'NIF {curie} deprecated',
                        makePrefixes('replacedBy', 'NIFRID', curie, *prefs),
                        f'{name}dead',
                        f'Classes from {curie} with owl:deprecated true that we want rdfs:subClassOf NIFRID:birnlexRetiredClass, or classes hiding in a oboInOwl:hasAlternativeId annotation. This file was generated by pyontutils/resurrect_id from {version}.')

    deads = [s for s in graph.subjects(rdflib.OWL.deprecated, rdflib.Literal(True))]
    for s in deads:
        types = set(o for o in graph.objects(s, rdflib.RDF.type))
        if anyMembers(types,
                      rdflib.OWL.AnnotationProperty,
                      rdflib.OWL.DataProperty,
                      rdflib.OWL.ObjectProperty):
            type_ =  'owl:DeprecatedProperty'
        elif rdflib.OWL.Class in types:
            type_ =  'owl:DeprecatedClass'
        else:
            continue  # don't bother with named individuals

        ng.add_trip(s, rdflib.RDFS.subClassOf, type_)

    base_alts = list(graph.subject_objects(og.expand('oboInOwl:hasAlternativeId')))
    for replacedByClass, oldClassString in base_alts:
        oldClassString = oldClassString.toPython()
        if ng.expand(oldClassString) not in deads:
            #if not alreadyHasEntry(oldClassString, og):
            ng.add_class(oldClassString, 'owl:DeprecatedClass')
            ng.add_trip(oldClassString, rdflib.OWL.deprecated, True)
            ng.add_trip(oldClassString, 'replacedBy:', replacedByClass)

    ng.write()

def main():
    if args['--slow'] or len(args['<file>']) == 1:
        [extract(f) for f in args['<file>']]
    else:
        with ProcessPoolExecutor(4) as ppe:
            futures = [ppe.submit(extract, _) for _ in args['<file>']]

if __name__ == '__main__':
    main()
