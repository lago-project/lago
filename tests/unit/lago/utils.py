from __future__ import absolute_import

import lago


def generate_workdir_props(**kwargs):
    default_props = {
        'loaded': False,
        'path': '.',
        'prefixes': {},
        'current': None,
        'prefix_class': lago.prefix.Prefix
    }
    default_props.update(kwargs)
    return default_props


def generate_workdir_params(**kwargs):
    if 'path' not in kwargs:
        kwargs['path'] = '.'
        return kwargs, generate_workdir_props(**kwargs)
