#
# Copyright 2014 Red Hat, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA
#
# Refer to the README and COPYING files for full details of the license
#
"""
About OutFormatPlugins

An OutFormatPlugin is used to format the output of the commands that extract
information from the perfixes, like status.
"""

import collections
import json
import yaml
from abc import (abstractmethod, ABCMeta)

from . import Plugin


class OutFormatPlugin(Plugin):
    __metaclass__ = ABCMeta

    def __init__(self):
        pass

    @abstractmethod
    def format(self, info_dict):
        """
        Execute any actions given the arguments

        Args:
            info_dict (dict): information to reformat

        Returns:
            str: String representing the formatted info
        """
        pass


class DefaultOutFormatPlugin(OutFormatPlugin):
    indent_unit = '    '

    def format(self, info_obj, indent=''):
        formatted_lines = []
        if isinstance(info_obj, list):
            if indent:
                formatted_lines.append('')
            for elem in info_obj:
                value_str = self.format(elem)
                formatted_lines.append(indent + value_str)
        elif isinstance(info_obj, collections.Mapping):
            for key in sorted(info_obj.keys()):
                value = info_obj[key]
                if isinstance(value, collections.Mapping):
                    if not value:
                        continue

                    formatted_lines.append('%s[%s]:' % (indent, str(key)))
                    value_str = self.format(
                        info_obj=value,
                        indent=indent + self.indent_unit,
                    )
                    if value_str:
                        formatted_lines.append(value_str)

                elif value not in (None, ''):
                    formatted_lines.append(
                        indent + str(key) + ': ' + self.format(
                            info_obj=value,
                            indent=indent + self.indent_unit,
                        )
                    )
        else:
            formatted_lines.append(str(info_obj))

        return '\n'.join(formatted_lines)


class JSONOutFormatPlugin(OutFormatPlugin):
    def format(self, info_dict):
        return json.dumps(info_dict, sort_keys=True, indent=4, )


class YAMLOutFormatPlugin(OutFormatPlugin):
    def format(self, info_dict):
        return yaml.dump(info_dict)
