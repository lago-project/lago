#!/usr/bin/env python2
import nose.tools as nt
from ovirtlago import testlib


@testlib.with_ovirt_prefix
def test_cpu_model_host(prefix):
    cpu_family = prefix.virt_env.get_ovirt_cpu_family()
    nt.assert_equals(cpu_family, 'Intel Westmere Family')


@testlib.with_ovirt_prefix
def test_cpu_model_engine(prefix):
    engine = prefix.virt_env.engine_vm()
    cpu_family = prefix.virt_env.get_ovirt_cpu_family(host=engine)
    nt.assert_equals(cpu_family, 'AMD Opteron G1')


@testlib.with_ovirt_prefix
def test_ssh(prefix):
    engine = prefix.virt_env.engine_vm()
    ret = engine.ssh(['hostname'])
    nt.assert_equals(ret.code, 0)


@testlib.with_ovirt_prefix
def test_service(prefix):
    engine = prefix.virt_env.engine_vm()
    nt.assert_true(engine.service('sshd').alive())
