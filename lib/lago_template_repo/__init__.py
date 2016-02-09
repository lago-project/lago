#!/usr/bin/python
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
import collections
import logging
import os
import sys

from lago import (config, utils)
from lago.plugins.cli import CLIPlugin


def do_add(args):
    ret, _, _ = utils.run_command(
        [
            'git',
            'clone',
            args.url,
        ],
        cwd=config.get('template_repos'),
    )
    if ret:
        raise RuntimeError('Failed to clone the repository')


def do_update(args):
    repos_dir = config.get('template_repos')
    ret, out, _ = utils.run_command(
        [
            'find', repos_dir, '-type', 'd', '-name', '.git'
        ],
    )

    for line in [l.strip() for l in out.split('\n') if len(l)]:
        repo_path = os.path.dirname(line)
        print 'Updating %s' % repo_path

        for command in [
            ['git', 'fetch'],
            ['git', 'reset', '--hard'],
            ['git', 'checkout', 'origin/master'],
        ]:
            ret, _, _ = utils.run_command(command, cwd=repo_path)
            if ret:
                raise RuntimeError('Error running: %s' % (' '.join(command)))


class Verbs:
    ADD = 'add'
    UPDATE = 'update'


ARGUMENTS = collections.OrderedDict()
ARGUMENTS[Verbs.ADD] = (
    'Add a git repository with JSON repo files to the directory with repos',
    (
        (
            'url',
            {
                'help': (
                    'Path to config that describes the scripts needed to run'
                ),
            },
        ),
    ),
    do_add,
)
ARGUMENTS[Verbs.UPDATE] = (
    'Update the saved repositories (to origin/master).',
    (),
    do_update,
)


class TemplateRepoCLI(CLIPlugin):
    init_args = {'help': 'Utility for system testing template management', }

    def populate_parser(self, parser):
        verbs = parser.add_subparsers(dest='tplverb', metavar='VERB')
        for verb, (desc, args, _) in ARGUMENTS.items():
            verb_parser = verbs.add_parser(verb, help=desc)
            for arg_name, arg_kw in args:
                verb_parser.add_argument(arg_name, **arg_kw)
        return parser

    def do_run(self, args):
        try:
            _, _, func = ARGUMENTS[args.tplverb]
            func(args)
        except Exception:
            logging.exception('Error occurred, aborting')
            sys.exit(1)
