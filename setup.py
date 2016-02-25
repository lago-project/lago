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
            'init=lago.cmd:do_init',
            'cleanup=lago.cmd:do_cleanup',
            'start=lago.cmd:do_start',
            'status=lago.cmd:do_status',
            'stop=lago.cmd:do_stop',
            'shell=lago.cmd:do_shell',
            'console=lago.cmd:do_console',
            'snapshot=lago.cmd:do_snapshot',
            'revert=lago.cmd:do_revert',
            'copy-from-vm=lago.cmd:do_copy_from_vm',
            'copy-to-vm=lago.cmd:do_copy_to_vm',
            'ovirt=ovirtlago.cmd:OvirtCLI',
            'template-repo=lago_template_repo:TemplateRepoCLI',
        ],
        'lago.plugins.output': [
            'default=lago.plugins.output:DefaultOutFormatPlugin',
            'json=lago.plugins.output:JSONOutFormatPlugin',
            'yaml=lago.plugins.output:YAMLOutFormatPlugin',
        ],
    },
)
