import pytest
import yaml
import textwrap
import tempfile
import os
import shutil
import logging
import uuid
from jinja2 import Environment, BaseLoader
from lago import sdk
from lago.utils import run_command


@pytest.fixture(scope='module')
def init_str(images):
    init_template = textwrap.dedent(
        """
    domains:
      {% for vm_name, template in images.viewitems() %}
      {{ vm_name }}:
        memory: 1024
        nics:
          - net: net-02
          - net: net-01
        disks:
          - template_name: {{ template }}
            type: template
            name: root
            dev: sda
            format: qcow2
        metadata:
            {{ vm_name }}: {{ vm_name }}
        artifacts:
          - /var/log
          - /etc/hosts
          - /etc/resolv.conf
          - /etc/sysconfig
          - /etc/NetworkManager
        groups: group{{ loop.index % 2 }}
      {% endfor %}

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
    template = Environment(loader=BaseLoader()).from_string(init_template)
    return template.render(images=images)


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
def external_log(tmpdir_factory):
    return tmpdir_factory.mktemp('external_log').join('custom_log.log')


@pytest.fixture(scope='module', autouse=True)
def env(request, init_fname, test_results, tmp_workdir, external_log):
    workdir = os.path.join(str(tmp_workdir), 'lago')
    env = sdk.init(
        init_fname,
        workdir=workdir,
        logfile=str(external_log),
        loglevel=logging.DEBUG,
    )
    env.start()
    yield env
    collect_path = os.path.join(test_results, 'collect')
    env.collect_artifacts(output_dir=collect_path, ignore_nopath=True)
    shutil.copytree(
        workdir,
        os.path.join(test_results, 'workdir'),
        ignore=shutil.ignore_patterns('*images*')
    )
    env.stop()
    env.destroy()


@pytest.fixture(scope='module')
def vms(env):
    return env.get_vms()


@pytest.fixture(scope='module')
def nets(env):
    return env.get_nets()


def test_custom_log(external_log):
    msg = "test_custom_log " + str(uuid.uuid4())
    logging.root.info(msg)
    with open(str(external_log), 'r') as f:
        assert msg in f.read()


def test_vms_exists(vms, init_dict):
    assert sorted(vms.keys()) == sorted(init_dict['domains'].keys())


def test_vms_networks_mapping(init_dict, vm_name, vms):
    vm = vms[vm_name]
    nics = [nic['net'] for nic in init_dict['domains'][vm_name]['nics']]
    assert sorted(vm.nets()) == sorted(nics)


def test_metadata(vm_name, vms):
    vm = vms[vm_name]
    metadata_spec = vm.spec['metadata']

    assert vm.metadata[vm_name] == metadata_spec[vm_name] == vm_name


def test_networks_exists(env, init_dict):
    nets = env.get_nets()
    assert sorted(nets.keys()) == sorted(init_dict['nets'].keys())


def test_custom_gateway(vms, nets, init_dict):
    for net_name, net in init_dict['nets'].iteritems():
        if 'gw' in net:
            assert nets[net_name].gw() == net['gw']


def test_vms_ssh(vms, vm_name):
    vm = vms[vm_name]
    assert vm.ssh_reachable(tries=200)


def test_vm_hostname_direct(vms, vm_name):
    vm = vms[vm_name]
    if any(distro in vm_name for distro in ['debian', 'ubuntu']):
        # hostname resolution in debian needs to be fixed, at the moment
        # it might return 'unassigned domain'
        pytest.skip('Broken on debian')
    assert 'dns_domain_name' in vm.mgmt_net.spec
    domain = vm.mgmt_net.spec['dns_domain_name']
    res = vm.ssh(['hostname', '-f'])
    assert res.code == 0
    assert str.strip(res.out) == '{0}.{1}'.format(vm.name(), domain)


@pytest.mark.check_merged
def test_vms_ipv4_dns(vms, vm_name):
    root = vms[vm_name]
    peers = [vm for vm in vms.values() if vm.name() != vm_name]
    for peer in peers:
        cmd = ['ping', '-c2']
        if not any(
            distro in vm_name for distro in ['el6', 'debian', 'ubuntu']
        ):
            cmd.append('-4')
        cmd.append(peer.name())
        res = root.ssh(cmd)
        assert res.code == 0


@pytest.mark.check_patch
@pytest.mark.skip('in CI after stop/start some of the VMs lost IP')
def test_load_env_down(env, tmp_workdir):
    env.stop()
    workdir = os.path.join(str(tmp_workdir), 'lago')
    logfile = os.path.join(str(tmp_workdir), 'lago-test_load_env_down.log')
    loaded_env = sdk.load_env(workdir, logfile=logfile)
    assert loaded_env is not env
    assert loaded_env._prefix is not env._prefix
    assert loaded_env._pprefix is not env._pprefix
    assert loaded_env._workdir is not env._workdir
    for vm in loaded_env.get_vms().values():
        assert vm.state() == 'down'
    loaded_env.start()
    for vm in loaded_env.get_vms().values():
        assert vm.ssh_reachable(tries=200)


@pytest.mark.check_patch
def test_load_env_up(env, vms, tmp_workdir):
    workdir = os.path.join(str(tmp_workdir), 'lago')
    logfile = os.path.join(str(tmp_workdir), 'lago-test_load_env_up.log')
    loaded_env = sdk.load_env(workdir, logfile=logfile)
    assert loaded_env is not env
    assert loaded_env._prefix is not env._prefix
    assert loaded_env._pprefix is not env._pprefix
    assert loaded_env._workdir is not env._workdir
    assert len(loaded_env.get_vms().values()) == len(vms.values())
    for vm in loaded_env.get_vms().values():
        assert vm.state() == 'running'
    for vm in loaded_env.get_vms().values():
        assert vm.ssh_reachable(tries=200)


@pytest.mark.check_merged
def test_ansible_inventory(monkeypatch, env, test_results, vms):

    # ansible returns the results in a bulk to stdout. Ideally we would test
    # forthe hostname of each machine, but that is broken on debian.
    # Instead, we let it compute something and count the unique occurences.

    cmd = 'echo __abcd$(( 24 + 12 ))efgh___'
    expected = '__abcd36efgh__'
    results = []

    with env.ansible_inventory_temp_file(keys=['groups']) as inv:
        for group in ['group0', 'group1']:
            logfile = os.path.join(
                test_results, 'ansible-{0}.log'.format(group)
            )
            monkeypatch.setenv('ANSIBLE_LOG_PATH', logfile)
            monkeypatch.setenv('ANSIBLE_HOST_KEY_CHECKING', 'False')
            res = run_command(
                [
                    'ansible', 'groups={0}'.format(group), '-v', '-u', 'root',
                    '-i', inv.name, '-m', 'raw', '-a', cmd
                ]
            )

            assert res.code == 0
            assert res.out is not None
            results.append(res)

    occurences = sum([result.out.count(expected) for result in results])

    assert occurences == len(vms.keys())
