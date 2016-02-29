import os
from setuptools import setup

setup(
    name='lago',
    version=os.environ['LAGO_VERSION'],
    description=(
        'Deploy and tear down environments of several virtual machines'
    ),
    license='GNU GPLv2+',
    author='David Caro',
    author_email='dcaro@redhat.com',
    url='http://lago.readthedocs.com',
    packages=[
        'lago',
        'lago.plugins',
        'lago_template_repo',
        'ovirtlago',
    ],
    provides=['lago', 'ovirtlago'],
)
