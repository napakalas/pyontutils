#!/usr/bin/env python3.6
from IPython import embed
import csv
from pathlib import Path
import rdflib
from pyontutils.neurons.compiled import neuron_data_lifted
ndl_neurons = neuron_data_lifted.Neuron.neurons()
embed()
from pyontutils.neurons.compiled import basic_neurons
bn_neurons = basic_neurons.Neuron.neurons()
from pyontutils.utils import byCol, relative_path
from pyontutils.core import resSource
from pyontutils.config import devconfig
from pyontutils.namespaces import interlex_namespace
# import these last so that graphBase resets (sigh)
from pyontutils.neurons.lang import *
from pyontutils.neurons import *

# TODO
# 1. inheritance for owlClass from python classes
# 2. add ttl serialization for subclasses of EBM
# 3. pv superclass for query example

class NeuronSWAN(NeuronEBM):
    owlClass = 'ilxtr:NeuronSWAN'

rename_rules = {'Colliculus inferior': 'Inferior colliculus',
                'Colliculus superior': 'Superior colliculus',
                'Premammillary nucleus dorsal': 'Dorsal premammillary nucleus',
                'Premammillary nucleus ventral': 'Ventral premammillary nucleus',
                'Septal complex lateral': 'Lateral septal complex',
                'Septal complex medial': 'Medial septal complex',
                'Substantia nigra pars reticulata': 'Reticular part of substantia nigra',
                'Thalamic reticular nucleus': 'Reticular thalamic nucleus',
                'Trigeminal nerve motor nucleus': 'Motor nucleus of trigeminal nerve',
                'Trigeminal nerve principal sensory nucleus': 'Principal sensory nucleus of trigeminal nerve',
                'Dorsal root ganglion cell': 'Dorsal root ganglion A alpha-beta non-nociceptive neuron',
                'Neocortex layer 2-3 pyramidal cell': 'Neocortex pyramidal layer 2-3 cell',
                #'Neocortex layer 5 pyramidal cell':  # TODO layer 5-6??
                'Hippocampus CA2 Basket cell': 'Hippocampus CA2 basket cell broad',
                'Neocortex layer 4 spiny stellate cell': 'Neocortex stellate layer 4 cell',
}

def main():
    resources = Path(devconfig.resources)
    cutcsv = resources / 'common-usage-types.csv'
    with open(cutcsv.as_posix(), 'rt') as f:
        rows = [l for l in csv.reader(f)]

    bc = byCol(rows)

    labels, *_ = zip(*bc)
    labels_set0 = set(labels)
    ns = []
    for n in ndl_neurons:
        l = n._origLabel
        for replace, match in rename_rules.items():  # HEH
            l = l.replace(match, replace)
        if l in labels:
            n._origLabel = l
            ns.append(n)

    embed()
    sns = set(n._origLabel for n in ns)

    labels_set1 = labels_set0 - sns

    agen = [c.label for c in bc if c.Autogenerated]
    sagen = set(agen)
    ans = []
    sans = set()
    missed = set()
    for n in bn_neurons:
        # can't use capitalize here because there are proper names that stay uppercase
        l = n.label.replace('(swannt) ',
                            '').replace('Intrinsic',
                                        'intrinsic').replace('Projection',
                                                             'projection')
        for replace, match in rename_rules.items():  # HEH
            l = l.replace(match, replace)

        if l in agen:
            n._origLabel = l
            ans.append(n)
            sans.add(l)
        else:
            missed.add(l)

    agen_missing = sagen - sans
    labels_set2 = labels_set1 - sans

    nlx_labels = [c.label for c in bc if c.Neurolex]
    snlx_labels = set(nlx_labels)

    class SourceCUT(resSource):
        sourceFile = 'pyontutils/resources/common-usage-types.csv'  # FIXME relative to git workingdir...
        source_original = True

    sources = SourceCUT(),
    swanr = rdflib.Namespace(interlex_namespace('swanson/uris/readable/'))
    Config('common-usage-types', sources=sources, source_file=relative_path(__file__),
           prefixes={'swanr':swanr,
                     'SWAN':interlex_namespace('swanson/uris/neuroanatomical-terminology/terms/'),
                     'SWAA':interlex_namespace('swanson/uris/neuroanatomical-terminology/appendix/'),})
    ins = [None] * len(ns)  # [n.id_ for n in ns]  # TODO
    ians = [None] * len(ans)
    new = [NeuronCUT(*n.pes, id_=i, label=n._origLabel, override=True) for i, n in zip(ins + ians, ns + ans)]
    # TODO preserve the names from neuronlex on import ...
    Neuron.write()
    Neuron.write_python()

    progress = len(labels_set0), len(sns), len(sans), len(labels_set1), len(labels_set2)
    print('\nProgress:\n'
          f'total:            {progress[0]}\n'
          f'from nlx:         {progress[1]}\n'
          f'from basic:       {progress[2]}\n'
          f'TODO after nlx:   {progress[3]}\n'
          f'TODO after basic: {progress[4]}\n')
    assert progress[0] == progress[1] + progress[3], 'neurolex does not add up'
    assert progress[3] == progress[2] + progress[4], 'basic does not add up'

    lnlx = set(n.lower() for n in snlx_labels)
    sos = set(n._origLabel.lower() for n in ndl_neurons)
    nlx_review = lnlx - sos
    print('\nNeuroLex listed as source but no mapping:', len(nlx_review))
    _ = [print(l) for l in sorted(nlx_review)]

    print('\nUnmapped:')
    _ = [print(l) for l in sorted(labels_set2)]

    if __name__ == '__main__':
        embed()


if __name__ == '__main__':
    main()
