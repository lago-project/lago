import os
from setuptools import setup

setup(
    name='lago',
    version=os.environ['LAGO_VERSION'],
    description=(
        'Deploy and tear down environments of several virtual machines'
    ),
    license='GNU GPLv2+',
    author='Dima Kuznetsov',
    author_email='dkuznets@redhat.com',
    url='redhat.com',
    package_dir={
        'lago': 'lib/lago',
        'ovirtlago': 'contrib/ovirt/lib/ovirtlago'
    },
    packages=['lago', 'ovirtlago'],
    package_data={
        'lago': [
            '*.xml',
            '*.log.conf',
        ],
    },
    provides=['lago', 'ovirtlago'],
    scripts=[
        'lago/lagocli',
        'lago/lagocli-template-repo',
        'contrib/ovirt/ovirtlago/lagocli-ovirt',
    ],
)
