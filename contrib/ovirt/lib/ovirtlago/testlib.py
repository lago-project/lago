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
import datetime
import functools
import os

import nose.plugins
from nose.plugins.skip import SkipTest

import lago.utils as utils

import ovirtlago

SHORT_TIMEOUT = 3 * 60
LONG_TIMEOUT = 10 * 60


_test_prefix = None


def get_test_prefix():
    if _test_prefix is None:
        global _test_prefix
        _test_prefix = ovirtlago.OvirtPrefix(os.getcwd())
    return _test_prefix


def with_ovirt_prefix(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(get_test_prefix(), *args, **kwargs)
    return wrapper


def with_ovirt_api(func):
    @functools.wraps(func)
    @with_ovirt_prefix
    def wrapper(prefix, *args, **kwargs):
        return func(
            prefix.virt_env.engine_vm().get_api(),
            *args,
            **kwargs
        )
    return wrapper


def continue_on_failure(func):
    func.continue_on_failure = True
    return func


def _vms_capable(vms, caps):
    caps = set(caps)
    vm_caps = lambda vm: set(vm.metadata.get('ovirt-capabilities', []))
    return caps.issubset(set.intersection(*[vm_caps(vm) for vm in vms]))


def engine_capability(caps):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            prefix = get_test_prefix()
            if not _vms_capable([prefix.virt_env.engine_vm()], caps):
                raise SkipTest()
            return func()
        return wrapper
    return decorator


def host_capability(caps):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            prefix = get_test_prefix()
            if not _vms_capable(prefix.virt_env.host_vms(), caps):
                raise SkipTest()
            return func()
        return wrapper
    return decorator


def test_sequence_gen(test_list):
    failure_occured = [False]
    for test in test_list:
        def wrapped_test():
            if failure_occured[0]:
                raise SkipTest()
            try:
                return test()
            except SkipTest:
                raise
            except:
                if not getattr(test, 'continue_on_failure', False):
                    failure_occured[0] = True
                raise
        wrapped_test.description = test.__name__
        yield wrapped_test


class LogCollectorPlugin(nose.plugins.Plugin):
    name = 'log-collector-plugin'

    def __init__(self, prefix):
        nose.plugins.Plugin.__init__(self)
        self._prefix = prefix

    def options(self, parser, env=None):
        env = env if env is not None else os.environ
        super(LogCollectorPlugin, self).options(parser, env)

    def configure(self, options, conf):
        super(LogCollectorPlugin, self).configure(options, conf)

    def addError(self, test, err):
        self._addFault(test, err)

    def addFailure(self, test, err):
        self._addFault(test, err)

    def _addFault(self, test, err):
        suffix = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        test_name = '%s-%s' % (test.id(), suffix)
        self._prefix.collect_artifacts(self._prefix.paths.test_logs(test_name))


def assert_true_within(func, timeout):
    with utils.EggTimer(timeout) as timer:
        while not timer.elapsed():
            try:
                if func():
                    return
            except Exception:
                pass
    raise AssertionError('Timed out')


def assert_true_within_short(func):
    assert_true_within(func, SHORT_TIMEOUT)


def assert_true_within_long(func):
    assert_true_within(func, LONG_TIMEOUT)
