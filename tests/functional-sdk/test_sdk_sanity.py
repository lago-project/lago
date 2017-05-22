import pytest
import yaml
import textwrap
import tempfile
import os
import shutil
from lago import sdk


@pytest.fixture(scope='module')
def init_str():
    return textwrap.dedent(
        """
    domains:
      vm-el73:
        memory: 1024
        nics:
          - net: net-02
          - net: net-01
        disks:
          - template_name: el7.3-base
            type: template
            name: root
            dev: sda
            format: qcow2
        artifacts:
          - /var/log
    nets:
      net-01:
        type: nat
        dhcp:
          start: 100
          end: 254
        management: true
        dns_domain_name: lago.local

      net-02:
        type: nat
        gw: 192.168.210.4
        dhcp:
          start: 100
          end: 254
    """
    )


@pytest.fixture(scope='module')
def init_dict(init_str):
    return yaml.load(init_str)


@pytest.fixture(scope='module')
def init_fname(init_str):
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(init_str)
    return f.name


@pytest.fixture(scope='module')
def test_results(request, global_test_results):
    results_path = os.path.join(
        global_test_results, str(request.module.__name__)
    )
    os.makedirs(results_path)
    return results_path


@pytest.fixture(scope='module')
def env(request, init_fname, test_results, tmp_workdir):
    workdir = os.path.join(tmp_workdir, 'lago')
    env = sdk.init(init_fname, workdir=workdir)
    env.start()
    yield env
    collect_path = os.path.join(test_results, 'collect')
    env.collect_artifacts(output_dir=collect_path, ignore_nopath=True)
    shutil.copytree(workdir, os.path.join(test_results, 'workdir'))
    env.stop()
    env.destroy()


@pytest.fixture(scope='module')
def vms(env):
    return env.get_vms()


@pytest.fixture(scope='module')
def nets(env):
    return env.get_nets()


def test_vms_exists(vms, init_dict):
    assert vms.keys() == init_dict['domains'].keys()


def test_vms_networks_mapping(init_dict, vms):
    for vm_name, vm in vms.iteritems():
        nics = [nic['net'] for nic in init_dict['domains'][vm_name]['nics']]
        assert sorted(vm.nets()) == sorted(nics)


@pytest.mark.timeout(100)
def test_vms_ssh(vms):
    for vm in vms.values():
        assert vm.ssh_reachable(tries=30)


@pytest.mark.timeout(100)
def test_vm_hostname_direct(vms, nets):
    for vm in vms.values():
        assert 'dns_domain_name' in vm.mgmt_net.spec
        domain = vm.mgmt_net.spec['dns_domain_name']
        res = vm.ssh(['hostname', '-f'])
        assert res.code == 0
        assert str.strip(res.out) == '{0}.{1}'.format(vm.name(), domain)


def test_networks_exists(env, init_dict):
    nets = env.get_nets()
    assert nets.keys() == init_dict['nets'].keys()


def test_custom_gateway(vms, nets, init_dict):
    for net_name, net in init_dict['nets'].iteritems():
        if 'gw' in net:
            assert nets[net_name].gw() == net['gw']
