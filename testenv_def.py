#!/usr/bin/python
import copy
import guestfs
import libvirt
import logging
import lxml.etree
import os
import sys
import threading
import utils

_dir_stack = []


IMAGES_DIR = '/var/lib/libvirt/images'
BASE_IMAGE = 'fedora20_root_template.img'

logfiles = {}


def create_network(name, gw):
    net_xml = lxml.etree.fromstring(open('net_template.xml').read())
    net_xml.xpath('/network/name')[0].text = name
    net_xml.xpath('/network/bridge')[0].attrib['name'] = '%s-nic' % name
    net_xml.xpath('/network/ip')[0].attrib['address'] = gw
    dhcp_range = net_xml.xpath('/network/ip/dhcp/range')[0]
    dhcp_range.attrib['start'] = '.'.join(gw.split('.')[:-1]) + '.100'
    dhcp_range.attrib['end'] = '.'.join(gw.split('.')[:-1]) + '.254'

    con = libvirt.open()
    con.networkDefineXML(lxml.etree.tostring(net_xml))
    network = con.networkLookupByName(name)
    network.create()
    network.setAutostart(True)


def destroy_network(name):
    con = libvirt.open()
    net = con.networkLookupByName(name)
    net.destroy()
    net.undefine()


def create_disk(name, spec):
    logging.debug("Creating disk for '%s': %s", name, spec)
    domain_img_name = '%s_%s.img' % (name, spec[0])
    if spec[1] == 'template':
        if len(spec) == 3:
            base = spec[2]
        else:
            base = BASE_IMAGE
        qemu_img_cmd = ['qemu-img', 'create', '-f', 'qcow2',
                        '-b', os.path.join(IMAGES_DIR, base),
                        domain_img_name]
    elif spec[1] == 'empty':
        qemu_img_cmd = ['qemu-img', 'create', '-f', 'qcow2',
                        domain_img_name, spec[2]]
    else:
        raise RuntimeError('Unknown drive spec %s' % str(spec))

    logging.debug('Running command: %s', ' '.join(qemu_img_cmd))
    ret, _, _ = utils.run_command(qemu_img_cmd, cwd=IMAGES_DIR)
    if ret != 0:
        logging.error('Failed creating disk, qemu-img returned with %d', ret)
        raise RuntimeError('Failed to create image for domain')

    disk_path = os.path.join(IMAGES_DIR, domain_img_name)
    logging.info('Successfully created disk at %s', disk_path)
    return disk_path

HOSTNAME_PATH = '/etc/hostname'
ISCSI_INITIATOR_NAME_PATH = '/etc/iscsi/initiatorname.iscsi'

SSH_DIR = '/root/.ssh'
AUTHORIZED_KEYS = '/root/.ssh/authorized_keys'

with open('/root/.ssh/id_rsa.pub') as f:
    HOST_PUB_KEY = f.read()


def bootstrap_domain(name, path):
    logging.debug("Dumping configuration to domain '%s' image %s",
                  name, path)
    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(path, format='qcow2', readonly=0)
    g.launch()
    g.mount('/dev/vg0/lv_root', '/')
    g.write(HOSTNAME_PATH, name + '\n')
    g.write(ISCSI_INITIATOR_NAME_PATH,
            'InitiatorName=iqn.2014-07.org.ovirt:%s\n' % name)
    try:
        g.mkdir(SSH_DIR)
    except RuntimeError:
        pass
    g.touch(AUTHORIZED_KEYS)
    g.write_append(AUTHORIZED_KEYS,
                   HOST_PUB_KEY)
    g.shutdown()
    g.close()
    logging.info("Successfully configured image for domain '%s'", name)


network_lock = threading.Lock()


def create_domain(name, info):
    logging.debug("Creating domain '%s', with the following spec: %s",
                  name, str(info))
    dom_xml = lxml.etree.fromstring(open('dom_template.xml').read())
    dom_xml.xpath('/domain/name')[0].text = name
    devices = dom_xml.xpath('/domain/devices')[0]

    # Mac addrs of domains are 54:52:xx:xx:xx:xx where the last 4 octets are
    # the hex repr of the IP address)
    mac_addr_pieces = [0x54, 0x52] + [int(y) for y in info['ip'].split('.')]

    mac_addr = ':'.join([('%02x' % x) for x in mac_addr_pieces])
    logging.debug("domain '%s': MAC = %s", name, mac_addr)

    net_if = devices.xpath('interface')[0]
    net_if.xpath('mac')[0].attrib['address'] = mac_addr
    net_if.xpath('source')[0].attrib['network'] = info['net']

    disk = devices.xpath('disk')[0]
    devices.remove(disk)

    for dev_spec in info['disks']:
        d = copy.deepcopy(disk)
        logging.debug("domain '%s': creating disk by this spec: %s",
                      name, str(dev_spec))
        d.xpath('source')[0].attrib['dev'] = create_disk(name, dev_spec[1:])
        d.xpath('target')[0].attrib['dev'] = dev_spec[0]
        devices.append(d)

    con = libvirt.open()

    with network_lock:
        network = con.networkLookupByName(info['net'])
        net_xml = lxml.etree.fromstring(network.XMLDesc())
        net_xml.xpath('/network/ip/dhcp')[0].append(
            lxml.etree.Element('host',
                               mac=mac_addr,
                               ip=info['ip'],
                               name=name))
        con.networkDefineXML(lxml.etree.tostring(net_xml))
        network.destroy()
        network.create()

    con.defineXML(lxml.etree.tostring(dom_xml))

    root_disk_path = os.path.join(IMAGES_DIR,
                                  '%s_%s.img' % (name, info['disks'][0][1]))
    bootstrap_domain(name, root_disk_path)

    return True


def start_and_setup_domain(name, info):
    # TODO createXML
    logging.info("Starting domain '%s'", name)
    libvirt.open().lookupByName(name).create()

    if 'script' in info:
        logging.info("Running script %s for domain '%s'", info['script'], name)
        utils.wait_for_ssh('root', info['ip'])
        utils.run_ssh_script('root', info['ip'], info['script'])
    return True


def destroy_domain(name, info):
    con = libvirt.open()
    dom = con.lookupByName(name)
    dom.destroy()
    dom.undefine()

    for disk in info['disks']:
        os.unlink(os.path.join(IMAGES_DIR,
                               '%s_%s.img' % (name, disk[1])))


# Network config
NETWORK_NAME = 'testenv'
NETWORK_PREFIX = '192.168.111.0'
define_ip = lambda suffix: '.'.join(NETWORK_PREFIX.split('.')[:-1]) + \
    '.' + str(suffix)
define_host = lambda id: {'ip': define_ip(10 + id),
                          'net': NETWORK_NAME,
                          'disks': [('vda', 'root', 'template',
                                     'host_template.img')],
                          'script': './setup_host.sh'}

# Domains config
domains = {'engine': {'ip': define_ip(2),
                      'net': NETWORK_NAME,
                      'disks': [('vda', 'root',
                                 'template', 'engine_template.img')],
                      'script': './setup_engine.sh'},
           'storage_iscsi': {'ip': define_ip(3),
                             'net': NETWORK_NAME,
                             'disks': [('vda', 'root', 'template'),
                                       ('vdb', 'extra1', 'empty', '30G')],
                             'script': './setup_storage_iscsi.sh'},
           'storage_nfs': {'ip': define_ip(4),
                           'net': NETWORK_NAME,
                           'disks': [('vda', 'root', 'template'),
                                     ('vdb', 'extra1', 'empty', '30G')],
                           'script': './setup_storage_nfs.sh'},
           'host0': define_host(0),
           'host1': define_host(1),
           'host2': define_host(2),
           'host3': define_host(3)}


if __name__ == '__main__':
    logging.basicConfig(
        stream=sys.stdout, level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    if sys.argv[1] == 'deploy':
        logging.info('Deploying testing environment...')
        logging.info('Creating bridge...')
        create_network(NETWORK_NAME, define_ip(1))

        # Create all domains
        logging.info('Creating virt domains...')

        vec = utils.func_vector(create_domain, domains.items())
        vt = utils.VectorThread(vec)
        vt.start_all()
        if not all(vt.join_all()):
            logging.error('Creation of one or more domains failed')
            raise RuntimeError('Failed to create domains')

        # Start all domains
        logging.info('Starting and setting up virt domains')
        vec = utils.func_vector(start_and_setup_domain, domains.items())
        vt = utils.VectorThread(vec)
        vt.start_all()
        if not all(vt.join_all()):
            logging.error('Start/setup of one or more domains failed')
            raise RuntimeError('Failed to start/setup domains')
        logging.info('Deploy done')

    elif sys.argv[1] == 'cleanup':
        destroy_network(NETWORK_NAME)
        for name, info in domains.iteritems():
            destroy_domain(name, info)
