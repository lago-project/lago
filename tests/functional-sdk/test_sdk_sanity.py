import pytest
import textwrap
import tempfile
import os
import logging
import uuid
import filecmp
from time import sleep

from jinja2 import Environment, BaseLoader
from lago import sdk
from lago.utils import run_command
from lago.plugins.vm import ExtractPathNoPathError
from utils import RandomizedDir


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
          - /should/not/exist
          - /root/custom
          - /var/log
          - /etc/hosts
          - /etc/resolv.conf
          - /etc/sysconfig
          - /etc/NetworkManager
          - /root/virt-sysprep-firstboot.log
          - /root/extract-{{ vm_name }}-dead
          - /root/extract-{{ vm_name }}-normal
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


@pytest.fixture
def randomized_dir(tmpdir):
    randomized_path = os.path.join(str(tmpdir), 'random')
    os.makedirs(randomized_path)
    return RandomizedDir(path=randomized_path, depth=5)


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


def test_vm_is_running(vms, vm_name):
    vm = vms[vm_name]
    assert vm.running()
    assert vm.state() == 'running'


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


def test_systemd_analyze(test_results, vms, vm_name):
    vm = vms[vm_name]
    retries = 3

    res = vm.ssh(['command', '-v', 'systemd-analyze'])
    if res.code != 0:
        raise pytest.skip(
            'systemd-analyze not available on {0}'.format(vm_name)
        )

    for i in range(retries):
        res = vm.ssh(['systemd-analyze'])
        if not res:
            break
        sleep(3)
    else:
        pytest.fail('Failed to run systemd-analyze on {}'.format(vm_name))

    log = '\n'.join([res.out, res.err])

    res = vm.ssh(['systemd-analyze', 'blame'])
    assert res.code == 0
    log = log + '\n'.join([res.out, res.err])
    fname = os.path.join(
        test_results, 'systemd-analyze-{0}.txt'.format(vm.name())
    )
    with open(fname, 'w') as out:
        out.write(log)


def test_collect_exists(tmpdir, vms, vm_name):
    path = '/root/custom'
    filename = 'test_file'
    custom_file = os.path.join(path, filename)

    content = 'nothing-{0}'.format(vm_name)

    vm = vms[vm_name]
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(content)

    res = vm.ssh(['mkdir', '-p', '/root/custom'])
    assert res.code == 0

    vm.copy_to(f.name, custom_file, recursive=False)

    vm.collect_artifacts(str(tmpdir), ignore_nopath=True)

    dest = os.path.join(str(tmpdir), path.replace('/', '_'), filename)
    with open(dest, 'r') as out_file:
        result = out_file.readlines()

    assert len(result) == 1
    assert result[0].strip() == content


def test_collect_raises(tmpdir, vms, vm_name):
    vm = vms[vm_name]
    dest = os.path.join(str(tmpdir), 'collect-failure')
    with pytest.raises(ExtractPathNoPathError):
        vm.collect_artifacts(dest, ignore_nopath=False)


# todo: Test extract_paths_dead once we figure why it's unstable in CI
@pytest.mark.parametrize('mode', (['normal', 'dead']))
def test_extract_paths(tmpdir, randomized_dir, vms, vm_name, mode):
    if mode == 'dead':
        pytest.skip('extract_paths_dead is not stable in CI')
    vm = vms[vm_name]
    dst = '/root/extract-{vm}-{mode}'.format(vm=vm_name, mode=mode)
    vm.copy_to(randomized_dir.path, dst, recursive=True)
    res = vm.ssh(['sync'])
    assert res.code == 0
    if mode == 'normal':
        extract = getattr(vm, 'extract_paths')
    elif mode == 'dead':
        extract = getattr(vm, 'extract_paths_dead')
    extracted_path = str(tmpdir)
    extract([(dst, extracted_path)], ignore_nopath=False)

    cmp_res = filecmp.dircmp(
        os.path.join(extracted_path, os.path.basename(dst)),
        randomized_dir.path
    )
    assert sorted(cmp_res.left_list) == sorted(cmp_res.right_list)


# todo: Test extract_paths_dead once we figure why it's unstable in CI
@pytest.mark.parametrize('mode', ['normal', 'dead'])
@pytest.mark.parametrize(
    'bad_path', ['/nothing/here', '/var/log/nested_nothing', '/root/nowhere']
)
def test_extract_paths_ignore_nopath(tmpdir, vms, vm_name, mode, bad_path):
    if mode == 'dead':
        pytest.skip('extract_paths_dead is not stable in CI')
    vm = vms[vm_name]
    dst = os.path.join(str(tmpdir), 'extract-failure')
    if mode == 'normal':
        extract = getattr(vm, 'extract_paths')
    elif mode == 'dead':
        extract = getattr(vm, 'extract_paths_dead')

    with pytest.raises(ExtractPathNoPathError):
        extract([(bad_path, dst)], ignore_nopath=False)

    extract([(bad_path, dst)], ignore_nopath=True)
