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
import functools
import logging
import os
import shutil
import sys
import tempfile
import time

import lago.utils as utils
from lago.prefix import Prefix

USAGE = """
%s UPDATE_DIR UPDATE_SCRIPT IMG1 ... IMGn
""" % sys.argv[0]

NETWORK_NAME = 'update-network'
name_index = 0


def domain_name(image_path):
    global name_index
    try:
        return 'update%02d-%s' % (name_index, os.path.basename(image_path))
    finally:
        name_index += 1


def updating(subject):
    return '%s.updating' % subject


if __name__ == '__main__':
    logging.basicConfig(
        stream=sys.stdout,
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    )

    working_dir = sys.argv[1]
    script_path = sys.argv[2]
    images = map(os.path.abspath, sys.argv[3:])

    with utils.RollbackContext() as rollback:
        # We will use each image we update as a snapshot, and if the update
        # is successfull we will merge
        for img in images:
            ret, _, _ = utils.run_command(
                [
                    'qemu-img', 'create', '-f', 'qcow2', '-b', img, updating(
                        img
                    )
                ]
            )
            if ret:
                raise RuntimeError('Failed to create copy of image')
            rollback.prependDefer(os.unlink, updating(img))
            # To avoid losing access once livirt changes ownership
            os.chmod(updating(img), 0666)

        config = {
            'nets': {
                NETWORK_NAME: {
                    'dhcp': {
                        'start': 100,
                        'end': 254,
                    },
                    'management': True,
                    'type': 'nat',
                },
            },
            'domains': {},
        }

        # Create a config we can use with lago
        for img in images:
            rc, out, _ = utils.run_command(['qemu-img', 'info', img])
            if rc != 0:
                raise RuntimeError('Failed to discover image format')
            image_format = [
                line.split()[-1]
                for line in out.split('\n') if line.startswith('file format:')
            ].pop()

            qemu_to_libvirt_formats = {'raw': 'file'}
            libvirt_format = qemu_to_libvirt_formats.get(
                image_format, image_format
            )

            dom_name = domain_name(img)
            dom_spec = {
                'nics': [
                    {
                        'net': NETWORK_NAME,
                    },
                ],
                'disks': [
                    {
                        'name': 'root',
                        'dev': 'vda',
                        'type': 'file',
                        'format': libvirt_format,
                        'path': updating(img),
                    },
                ],
                'metadata': {
                    'image_path': img,
                },
            }
            config['domains'][dom_name] = dom_spec

        temp_dir = tempfile.mkdtemp(suffix='-domain-updater')
        rollback.prependDefer(shutil.rmtree, temp_dir)

        prefix = Prefix(working_dir)
        prefix.initialize()
        rollback.prependDefer(shutil.rmtree, working_dir)
        rollback.prependDefer(prefix.cleanup)

        prefix.virt_conf(config)
        prefix.start()

        jobs = []
        images_to_merge = []
        for vm in prefix.virt_env.get_vms().values():

            def update_domain(vm):
                vm.wait_for_ssh()
                ret, _, _ = vm.ssh_script(script_path)

                # Do not commit image if script returned with error.
                if ret:
                    return

                vm.ssh(['sync'])
                vm.ssh(['shutdown', '-h', 'now'])

                while vm.alive():
                    time.sleep(0.1)

                images_to_merge.append(vm.metadata['image_path'])

            jobs.append(functools.partial(update_domain, vm))

        # ssh into all domains and update
        vt = utils.VectorThread(jobs)
        vt.start_all()
        vt.join_all(raise_exceptions=False)

        # We only merge the successfully updated images
        for image_path in images_to_merge:
            ret, _, _ = utils.run_command(
                ['qemu-img', 'commit', updating(image_path)]
            )
            if ret:
                raise RuntimeError('Failed to commit changes to template')

        if not images_to_merge:
            logging.info('No images to commit')
            sys.exit(1)
