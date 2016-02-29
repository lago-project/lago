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
import BaseHTTPServer
import contextlib
import os
import threading
import SimpleHTTPServer

import lago.utils as utils

import constants


def run_command(command, **kwargs):
    """
    Wrapper around :func:`lago.utils.run_command` that prepends the ovirtlago
    LIBEXEC_DIR to the path if needed

    Args:
        command (?): parameter to send as the command parameter to
            :func:`lago.utils.run_command`
        **kwargs (?): keyword parameters to send as the command parameter to
            :func:`lago.utils.run_command`

    Returns:
        ?: Whatever :func:`lago.utils.run_command` returns
    """
    # add libexec to PATH if needed
    if constants.LIBEXEC_DIR not in os.environ['PATH'].split(':'):
        os.environ['PATH'] = '%s:%s' % (
            constants.LIBEXEC_DIR, os.environ['PATH']
        )
    return utils.run_command(command, **kwargs)


def _BetterHTTPRequestHandler(root_dir):
    """
    Factory for _BetterHTTPRequestHandler classes

    Args:
        root_dir (path): Path to the dir to serve

    Returns:
        _BetterHTTPRequestHandler: A ready to be used improved http request
            handler
    """
    _SimpleHTTPRequestHandler = SimpleHTTPServer.SimpleHTTPRequestHandler

    class _BetterHTTPRequestHandler(_SimpleHTTPRequestHandler):
        __root_dir = root_dir

        def translate_path(self, path):
            return os.path.join(
                self.__root_dir, _SimpleHTTPRequestHandler.translate_path(
                    self, path
                )[len(os.getcwd()):].lstrip('/')
            )

        def log_message(self, *args, **kwargs):
            pass

    return _BetterHTTPRequestHandler


def _create_http_server(ip, port, root_dir):
    """
    Starts an http server with an improved request handler

    Args:
        ip (str): Ip to listen on
        port (int): Port to register on
        root_dir (str): path to the directory to serve

    Returns:
        BaseHTTPServer: instance of the http server, already running on a
            thread
    """
    server = BaseHTTPServer.HTTPServer(
        (ip, port),
        _BetterHTTPRequestHandler(root_dir),
    )
    threading.Thread(target=server.serve_forever).start()
    return server


@contextlib.contextmanager
def repo_server_context(prefix):
    """
    Context manager that starts an http server that serves the given prefix's
    yum repository. Will listen on :class:`constants.REPO_SERVER_PORT` and on
    the first network defined in the previx virt config

    Args:
        prefix(ovirtlago.OvirtPrefix): prefix to start the server for

    Returns:
        None
    """
    gw_ip = prefix.virt_env.get_net().gw()
    port = constants.REPO_SERVER_PORT
    server = _create_http_server(gw_ip, port, prefix.paths.internal_repo())
    try:
        yield
    finally:
        server.shutdown()
