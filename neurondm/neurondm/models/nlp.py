import re
from collections import defaultdict
from urllib.parse import quote as url_quote
import rdflib
from pyontutils.sheets import Sheet
from pyontutils.namespaces import ilxtr, TEMP, rdfs, skos, owl, interlex_namespace
from neurondm.core import Config, NeuronEBM, Phenotype, NegPhenotype, log, OntCuries, OntId, add_partial_orders, IntersectionOf
from neurondm import orders


class NeuronSparcNlp(NeuronEBM):
    owlClass = ilxtr.NeuronSparcNlp
    shortname = 'sprcnlp'


class NLP1(Sheet):
    name = 'off-nlp-1'


class NLP2(Sheet):
    name = 'off-nlp-2'


class NLPSemVes(Sheet):
    name = 'off-nlp-il-semves'


class NLPProst(Sheet):
    name = 'off-nlp-il-prostate'


class NLPFemrep(Sheet):
    name = 'off-nlp-il-femrep'


class NLPFemreprat(NLPFemrep):
    pass


class NLPSenseMotor(Sheet):
    name = 'sensory-motor'


class NLPLiver(Sheet):
    name = 'off-nlp-liv'


class NLPKidney(Sheet):
    name = 'off-nlp-kid'


class NLPSwglnd(Sheet):
    name = 'off-nlp-swglnd'


def nlp_ns(name):
    return rdflib.Namespace(interlex_namespace(f'tgbugs/uris/readable/sparc-nlp/{name}/'))


snames = {
    'MM Set 1': (NLP1, nlp_ns('mmset1'), None),
    'MM Set 2 Cranial Nerves': (NLP1, nlp_ns('mmset2cn'), 'cranial nerves'),
    'MM Set 4': (NLP2, nlp_ns('mmset4'), None),
    'Seminal Vesicles': (NLPSemVes, nlp_ns('semves'), 'seminal vesicles'),
    'Prostate': (NLPProst, nlp_ns('prostate'), 'prostate'),
    '1. Female Reproductive-HUMAN': (NLPFemrep, nlp_ns('femrep'), 'female reproductive system human'),
    '3. Female-RAT': (NLPFemreprat, nlp_ns('femrep'), 'female reproductive system rat'),  # separate sheet ids differ
    'All SM connections': (NLPSenseMotor, nlp_ns('senmot'), 'sensory motor'),
    'ALL Liver_Human_Rat_Mouse': (NLPLiver, nlp_ns('liver'), 'liver'),
    'All KIDNEY connections': (NLPKidney, nlp_ns('kidney'), 'kidney'),
    'Sheet1': (NLPSwglnd, nlp_ns('swglnd'), 'sweat glands'),
    'comprt': (type('ComposerRT', (object,), dict()), None, 'composer round trip'),
}


sheet_classes = [
    type(f'{base.__name__}{sname.replace(" ", "_")}',
         (base,), dict(sheet_name=sname))
    for sname, (base, ns, working_set) in snames.items()
    if ns is not None]


def map_predicates(sheet_pred, prefix=ilxtr):
    p = {
        '': TEMP.BROKEN_EMPTY,
        'Soma': prefix.hasSomaLocatedIn,
        'Axon terminal': prefix.hasAxonPresynapticElementIn,
        'Axon': prefix.hasAxonLocatedIn,
        'Dendrite': prefix.hasDendriteLocatedIn,
        'Axon sensory terminal': prefix.hasAxonSensorySubcellularElementIn,
        'hasInstanceInTaxon': prefix.hasInstanceInTaxon,
        'hasPhenotype': prefix.hasPhenotype,
        'hasAnatomicalSystemPhenotype': prefix.hasAnatomicalSystemPhenotype,
        'hasBiologicalSex': prefix.hasBiologicalSex,
        'hasCircuitRole': prefix.hasCircuitRolePhenotype,  # used in femrep
        'hasCircuitRolePhenotype': prefix.hasCircuitRolePhenotype,
        'hasForwardConnectionPhenotype': prefix.hasForwardConnectionPhenotype,  # FIXME this needs to be unionOf
        'Axon-Leading-To-Sensory-Terminal': prefix.hasAxonLeadingToSensorySubcellularElementIn,

        # from composer
        'hasSomaLocatedIn': prefix.hasSomaLocatedIn,
        'hasAxonLocatedIn': prefix.hasAxonLocatedIn,
        'hasAxonPresynapticElementIn': prefix.hasAxonPresynapticElementIn,
        'hasAxonSensorySubcellularElementIn': prefix.hasAxonSensorySubcellularElementIn,
        'hasProjection': prefix.hasProjectionPhenotype,  # XXX check the semantics on this one
        'hasProjectionLaterality': prefix.hasProjectionLaterality,  # XXX check the semantics on this one because it expects contra/ipsi not left/right
        'hasSomaPhenotype': prefix.hasSomaPhenotype,  # XXX what is this being used for? I can't find any objects?
    }[sheet_pred]
    return p


def ind_to_adj(ind_uri):
    inds = sorted(set([i for i, u in ind_uri]))
    edges = []
    for a, b in zip(inds[:-1], inds[1:]):
        for i, iu in ind_uri:
            # XXX yes this is a horribly inefficient way to do this
            # index them in a dict if it becomes an issue
            if i == a:
                for j, ju in ind_uri:
                    if j == b:
                        edge =  iu, ju
                        edges.append(edge)

    return edges


def main(debug=False, cs=None, config=None, neuron_class=None):
    def derp(v):
        class sigh:
            value = v
        return sigh

    OntCuries({'ISBN13': 'https://uilx.org/tgbugs/u/r/isbn-13/',})
    if cs is None:
        cs = [c() for c in sheet_classes]

    trips = [[cl] + [c if isinstance(c, OntId) else c.value for c in
                     ((r.id() if hasattr(r, 'id') else OntId(r.uri().value)),
                      (r.predicate() if hasattr(r, 'predicate') else r.relationship()),
                      (r.identifier() if r.identifier().value.strip() else
                       derp(TEMP['MISSING_' + r.structure().value.replace(' ', '-')])))]
             for cl in cs for r in cl.rows()
             if r.row_index > 0 and (r.id().value if hasattr(r, 'id') else r.uri().value)
             #and (not hasattr(r, 'exclude') or not r.exclude().value)
             and r.proposed_action().value.lower() != "don't add"
             ]

    to_add = []

    def vl(meth):
        return rdflib.Literal(meth().value)

    def asdf(s, p, rm, split=False, rdf_type=rdflib.Literal):
        v = vl(rm)
        if v:
            # XXX watch out for non-homogenous subject types
            # (e.g. OntId vs rdflib.URIRef)
            if split:
                for _v in v.split(split):
                    to_add.append((s.u, p, rdf_type(_v.strip())))
            else:
                to_add.append((s.u, p, v))

    def lcc(uri_or_curie):
        if '<' in uri_or_curie:
            # see pyontutils.utils_extra check_value
            return rdflib.URIRef(url_quote(uri_or_curie, ':/;()'))
        else:
            return OntId(uri_or_curie).u

    dd = defaultdict(list)
    ec = {}
    def wrap(s):
        class cl:
            value = s
        def inner(_=cl):
            return _

        return inner

    for cl in cs:
        _, nlpns, working_set = snames[cl.sheet_name]
        log.debug(f'working on {working_set}')
        for r in cl.rows():
            try:
                if (r.row_index > 0 and
                    (r.id if hasattr(r, 'id') else r.uri)().value and
                    r.proposed_action().value.lower() != "don't add"):
                    # extra trips
                    #print(repr(r.id()))
                    _id = (r.id().value if hasattr(r, 'id') else OntId(r.uri().value))
                    _prefix = nlpns.split('/')[-2] if hasattr(r, 'id') else 'comprt'
                    s = _id if isinstance(_id, OntId) else OntId(nlpns[_id])
                    #print(s)
                    if hasattr(r, 'sentence_number'):
                        asdf(s, ilxtr.sentenceNumber, r.sentence_number)
                    if hasattr(r, 'different_from_existing'):
                        asdf(s, ilxtr.curatorNote, r.different_from_existing)
                    asdf(s, ilxtr.curatorNote, r.curation_notes)
                    asdf(s, ilxtr.reviewNote, r.review_notes)
                    asdf(s, ilxtr.reference, r.reference_pubmed_id__doi_or_text)
                    if hasattr(r, 'literature_citation'):
                        asdf(s, ilxtr.literatureCitation, r.literature_citation, split=',', rdf_type=lcc)
                    asdf(s, ilxtr.origLabel, r.neuron_population_label_a_to_b_via_c)
                    asdf(s, skos.prefLabel, r.neuron_population_label_a_to_b_via_c)
                    asdf(s, rdfs.label, wrap(f'neuron type {_prefix} {_id}'))
                    if hasattr(r, 'alert_explanation'):
                        asdf(s, ilxtr.alertNote, r.alert_explanation)

                    if hasattr(r, 'explicit_complement') and r.explicit_complement().value:
                        p = map_predicates(r.relationship().value)
                        o = OntId(r.explicit_complement().value)
                        ec[(s, p)] = o

                    if hasattr(r, 'axonal_course_poset') and r.axonal_course_poset().value:
                        # s.u and OntId(...).u to avoid duplicate subjects/objects in the graph
                        # due to type vs instance issues for rdflib.URIRef and OntId
                        _v = r.identifier().value
                        if not _v:
                            _structure = r.structure().value
                            _alt_v = TEMP['MISSING_' + _structure.replace(' ', '-')]
                        else:
                            _structure = r.structure().value
                            _alt_v = TEMP.BROKEN_EMPTY

                        if not debug and not _v:
                            raise ValueError(f'row missing object for {_structure}')

                        if _v and ',' in _v:
                            _r, _l = [_.strip() for _ in _v.split(',')]
                            #_v = _r  # FIXME TODO handle rl pairs
                            _obj = orders.rl(region=OntId(_r).u, layer=OntId(_l).u)
                        else:
                            try:
                                _obj = OntId(_v).u if _v else _alt_v
                            except OntId.UnknownPrefixError as e:
                                if debug:
                                    log.exception(e)
                                    _obj = TEMP.BROKEN_MALFORMED
                                else:
                                    raise e

                            _obj = orders.rl(region=_obj)

                        dd[s.u].append((int(r.axonal_course_poset().value), _obj))

                    if working_set:
                        class v:
                            value = working_set
                        asdf(s, ilxtr.inNLPWorkingSet, lambda x=v: x)

            except Exception as e:
                msg = f'\nbad row: | {" | ".join(r.values)} |'
                log.error(msg)
                raise e

    sorders = {k:sorted(v) for k, v in dd.items()}
    sadj = {k:ind_to_adj(v) for k, v in sorders.items()}
    snst = {k:orders.adj_to_nst(v) for k, v in sadj.items()}

    # XXX config must be called before creating any phenotypes
    # otherwise in_graph will not match when we go to serialize
    if config is None:
        config = Config('sparc-nlp')

    dd = defaultdict(list)
    for c, _s, _p, _o in trips:
        _, nlpns, working_set = snames[c.sheet_name]
        for x in (_s, _p, _o):
            if re.match(r'(^[\s]+[^\s].*|.*[^\s][\s]+$)', x):
                msg = f'leading/trailing whitespace in {c} {_s!r} {_p!r} {_o!r}'
                log.error(msg)
                raise ValueError(msg)

        s = _s if isinstance(_s, OntId) else OntId(nlpns[_s])
        try:
            p = map_predicates(_p)
        except KeyError as e:
            log.error(f'sigh {s}')
            raise e

        if not _o:  # handle empty cell case
            msg = f'missing object? {s.curie} {OntId(p).curie} ???'
            log.error(msg)
            if not debug:
                raise ValueError(msg)
            else:
                _o = TEMP.BROKEN_EMPTY

        elif nlpns is None:
            if ',' in _o:
                _r, _l = [_.strip() for _ in _o.split(',')]
                _o = IntersectionOf(OntId(_r).u, OntId(_l).u)
                #_o = _r  # FIXME TODO handle region/layer
        elif p == ilxtr.hasForwardConnectionPhenotype:
            _o = nlpns[_o]

        if isinstance(_o, IntersectionOf):
            o = _o
        else:
            try:
                o = OntId(_o)
            except OntId.UnknownPrefixError as e:
                if debug:
                    log.exception(e)
                    o = TEMP.BROKEN_MALFORMED_2
                else:
                    raise e

        if p == owl.equivalentClass:
            to_add.append((s.u, p, o.u))
            continue

        try:
            dd[s].append(Phenotype(o, p))
        except TypeError as e:
            log.error(f'bad data for {c} {s} {p} {o}')
            raise e

        if ec and (s, p) in ec:
            dd[s].append(NegPhenotype(ec[(s, p)], p))


    if neuron_class is None:
        neuron_class = NeuronSparcNlp
    sigh = []
    nrns = []
    for id, phenos in dd.items():
        n = neuron_class(*phenos, id_=id)
        if False and eff(n):
            n._sigh()  # XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX FIXME figure out why this is not getting called internally
            sigh.append(n)

        nrns.append(n)

    def sigh_bind(n, p):  # XXX FIXME UGH
        Phenotype.in_graph.bind(n, p)

    # FIXME these must also be in nifstd/scigraph/curie_map.yaml to show up on export
    sigh_bind('mmset4', snames['MM Set 4'][1])
    sigh_bind('semves', snames['Seminal Vesicles'][1])
    sigh_bind('prostate', snames['Prostate'][1])
    sigh_bind('femrep', snames['1. Female Reproductive-HUMAN'][1])
    sigh_bind('senmot', snames['All SM connections'][1])
    sigh_bind('kidney', snames['All KIDNEY connections'][1])
    sigh_bind('liver', snames['ALL Liver_Human_Rat_Mouse'][1])
    sigh_bind('swglnd', snames['Sheet1'][1])

    config.write()
    labels = (
        #ilxtr.genLabel,
        ilxtr.localLabel, ilxtr.simpleLabel,
        ilxtr.simpleLocalLabel, rdfs.label, skos.prefLabel)
    to_remove = [t for t in config._written_graph if t[1] in labels]
    [config._written_graph.remove(t) for t in to_remove]
    [config._written_graph.add(t) for t in to_add]
    add_partial_orders(config._written_graph, snst)
    # uncomment to debug type vs instance issues
    #sigh = sorted(set(s for s in config._written_graph.subjects() if isinstance(s, rdflib.URIRef)))
    config._written_graph.write()
    config.write_python()
    return config,


if __name__ == '__main__':
    main()
