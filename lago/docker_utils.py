#
# Copyright 2016 Red Hat, Inc.
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
Utilities to help deal with the docker python bindings
"""
from docker import Client

#: Singleton with the cached opened docker clients
DOCKER_CLIENTS = {}


class Container(object):
    """
    Class to namespace docker container related helpers
    """


def get_docker_client(name, docker_url='unix://var/run/docker.sock'):
    if name not in DOCKER_CLIENTS:
        DOCKER_CLIENTS[name] = Client(docker_url)

    return DOCKER_CLIENTS[name]
