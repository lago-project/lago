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
import getopt
import logging
import os
import sys
import tempfile
import uuid

import testenv.utils as utils
import testenv.dirlock as dirlock

USAGE = """
%s [--create CLONE_URL] PATH
Sync the templates located in PATH to ones in the remote git repository
If --create provided, a new repository is initialized at PATH.
""" % sys.argv[0]


def initialize(templates_dir, clone_url):
    if os.path.exists(templates_dir):
        raise RuntimeError('Failed to initialize, path exists')
    os.makedirs(templates_dir)

    # Clone remote repo:
    ret, _, _ = utils.run_command(['git', 'clone', clone_url, 'git-repo'],
                                  cwd=templates_dir)
    if ret != 0:
        raise RuntimeError('Failed to clone remote repository')


def qemu_img_convert(frm, frm_format, to, to_format):
    return utils.run_command(['qemu-img', 'convert',
                              '-f', frm_format, frm,
                              '-O', to_format, to])


def update(templates_dir):
    logging.info('Updating template directory at %s', templates_dir)

    git_repo = os.path.join(templates_dir, 'git-repo')

    ret, _, _ = utils.run_command(['git', 'fetch', 'origin'], cwd=git_repo)
    if ret != 0:
        logging.warning('Failed to access templates git repo')
        return

    ret, local_head, _ = utils.run_command(
        ['git', 'rev-parse', 'master'], cwd=git_repo)
    if ret != 0:
        raise RuntimeError('Failed to retrieve current revision')

    logging.debug('Fetching from remote repository')
    ret, remote_head, _ = utils.run_command(
        ['git', 'rev-parse', 'origin/master'], cwd=git_repo)
    if ret != 0:
        raise RuntimeError('Failed to retrieve remote revision')

    if remote_head != local_head:
        logging.debug('Local repository is not up to date, rebasing')
        ret, _, _ = utils.run_command(
            ['git', 'rebase', 'origin/master'], cwd=git_repo)
        if ret != 0:
            raise RuntimeError('Failed to rebase on remote master')

    for root, dirs, files in os.walk(git_repo):
        dirs[:] = [d for d in dirs if d != '.git']

        for filename in files:
            logging.debug('Checking if %s needs update.', filename)
            path_in_git = os.path.join(root, filename)
            rel_path = path_in_git[len(git_repo):].lstrip('/')
            path_outside_git = os.path.join(templates_dir, rel_path)

            try:
                with open('%s.hash' % path_outside_git) as f:
                    current_rev = f.read()
            except IOError:
                current_rev = ''

            ret, updated_rev, _ = utils.run_command(
                ['git', 'log', '-n', '1',
                 '--pretty=format:%H', '--', rel_path],
                cwd=git_repo)
            if ret != 0:
                raise RuntimeError('Failed to retrieve image revision')

            if current_rev != updated_rev:
                logging.debug('Updating %s', filename)
                if os.path.exists(path_outside_git):
                    os.unlink(path_outside_git)
                elif not os.path.exists(os.path.dirname(path_outside_git)):
                    os.makedirs(os.path.dirname(path_outside_git))
                ret, _, _ = qemu_img_convert(path_in_git, 'qcow2',
                                             path_outside_git, 'raw')

                if ret != 0:
                    raise RuntimeError('Failed to convert image')

                with open('%s.hash' % path_outside_git, 'w') as f:
                    f.write(updated_rev)


if __name__ == '__main__':
    logging.basicConfig(
        stream=sys.stdout, level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    optlist, args = getopt.gnu_getopt(sys.argv[1:], '', ['create='])

    templates_dir = args[0]
    create_url = None
    for opt, arg in optlist:
        if opt == '--create':
            create_url = arg

    if create_url:
        initialize(templates_dir, create_url)

    fd, temp_path = tempfile.mkstemp()
    os.write(fd, uuid.uuid1().hex)
    os.close(fd)
    try:
        if dirlock.trylock(templates_dir, True, temp_path):
            logging.info('Successfully locked templates directory')
            update(templates_dir)
        else:
            logging.info('Skipping templates update, templates in use')
    finally:
        os.unlink(temp_path)
