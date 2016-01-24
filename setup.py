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
        'lago_template_repo': 'lib/lago_template_repo',
        'ovirtlago': 'contrib/ovirt/lib/ovirtlago'
    },
    packages=[
        'lago',
        'lago.plugins',
        'lago_template_repo',
        'ovirtlago',
    ],
    package_data={
        'lago': [
            '*.xml',
            '*.log.conf',
        ],
    },
    provides=['lago', 'ovirtlago'],
    entry_points={
        'console_scripts': [
            'lagocli=lago.cmd:main',
            'lago=lago.cmd:main',
        ],
        'lago.plugins.cli': [
            'ovirt=ovirtlago.cmd:OvirtCLI',
            'template-repo=lago_template_repo:TemplateRepoCLI',
        ],
    },
)
