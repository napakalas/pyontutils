from setuptools import setup

with open('README.md', 'rt') as f:
    long_description = f.read()

tests_require = ['pytest', 'pytest-runner']
setup(
    name='pyontutils',
    version='0.1.0',
    description='utilities for working with the NIF ontology, SciGraph, and turtle',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/tgbugs/pyontutils',
    author='Tom Gillespie',
    author_email='tgbugs@gmail.com',
    license='MIT',
    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ],
    keywords='ontology scigraph rdflib turtle ttl OWL',
    packages=['pyontutils'],
    python_requires='>=3.6',
    tests_require=tests_require,
    install_requires=[
        'docopt',
        'gitpython',
        'google-api-python-client',
        'hyputils',
        'ipython',
        'joblib',
        'lxml',
        'oauth2client',
        'ontquery>=0.0.7',
        'psutil',
        'pyyaml',
        'neurdflib',
        'requests',
        'robobrowser',
        'ttlser',
    ],
    extras_require={'dev': ['hunspell',
                            'jupyter',
                            'mysql-connector',
                            'protobuf',
                            'psycopg2',
                           ],
                    'test': tests_require,
                   },
    #package_data
    #data_files=[('resources',['pyontutils/resources/chebi-subset-ids.txt',])],  # not part of distro
    entry_points={
        'console_scripts': [
            'graphml-to-ttl=pyontutils.graphml_to_ttl:main',
            'ilxcli=pyontutils.ilxcli:main',
            'necromancy=pyontutils.necromancy:main',
            'ont-catalog=pyontutils.make_catalog:main',
            'ontload=pyontutils.ontload:main',
            'ontutils=pyontutils.ontutils:main',
            'overlaps=pyontutils.overlaps:main',
            'qnamefix=pyontutils.qnamefix:main',
            'scigraph-codegen=pyontutils.scigraph_codegen:main',
            'scigraph-deploy=pyontutils.scigraph_deploy:main',
            'scig=pyontutils.scig:main',
        ],
    },
)
