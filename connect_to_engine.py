#! /usr/bin/python

from ovirtsdk.api import API
from ovirtsdk.xml import params
from time import sleep
import threading

VERSION = params.Version(major='3', minor='4')

URL =           'https://192.168.111.2/ovirt-engine/api'
USERNAME =      'admin@internal'
PASSWORD =      '123'
api = API(url=URL, username=USERNAME, password=PASSWORD,
          validate_cert_chain=False, insecure=True)

def create_dc(name):
    if api.datacenters.add(params.DataCenter(name=name, storage_type='iscsi', version=VERSION)):
        print 'iSCSI Data Center was created successfully'

CPU_TYPE = 'Intel Conroe Family'

def create_cluster(name, dc):
    if api.clusters.add(params.Cluster(name=name, cpu=params.CPU(id=CPU_TYPE), data_center=api.datacenters.get(dc), version=VERSION)):
        print 'Cluster was created successfully'

def install_host(ip, name, dc, cluster, wait=False):
    try:
       if api.hosts.add(params.Host(name=name, address=ip, cluster=api.clusters.get(cluster), root_password='qum5net')):
           print 'Host was installed successfully'
           if wait:
               print 'Waiting for host to reach the Up status'
               while api.hosts.get(name).status.state != 'up':
                   sleep(1)
               print "Host is up"
    except Exception as e:
       print 'Failed to install Host:\n%s' % str(e)

def add_iscsi_storage(addr, target, luns, name, host, dc):
    lun_params = map(lambda l: params.LogicalUnit(id=l,
                                                  address=addr,
                                                  port=3260,
                                                  target=target), luns)
    sdParams = params.StorageDomain(name=name,
                                    data_center=api.datacenters.get(dc),
                                    type_='data',
                                    host=api.hosts.get(host),
                                    storage = params.Storage(type_='iscsi',
                                                             volume_group=params.VolumeGroup(logical_unit=lun_params)))
    try:
        if api.storagedomains.add(sdParams):
            print 'iSCSI Storage Domain was created successfully'
    except Exception as e:
        print 'Failed to create iSCSI Storage Domain:\n%s' % str(e)
        return
    try:
        if api.datacenters.get(dc).storagedomains.add(api.storagedomains.get(name)):
                print 'iSCSI Storage Domain was attached successfully'
    except Exception as e:
        print 'Failed to attach iSCSI Storage Domain:\n%s' % str(e)

def add_nfs_storage(addr, path, name, host, dc):
    p = params.StorageDomain(name=name,
                             data_center=api.datacenters.get(dc),
                             type_='data',
                             host=api.hosts.get(host),
                             storage = params.Storage(type_='nfs',
                                                      address=addr,
                                                      path=path))
    try:
        if api.storagedomains.add(p):
            print 'Data Domain was created/imported successfully'
        if api.datacenters.get(dc).storagedomains.add(api.storagedomains.get(name)):
            print 'Data Domain was attached successfully'
    except Exception as e:
        print 'Failed to add export domain:\n%s' % str(e)


create_dc('test')
create_cluster('test', 'test')
threads = []
threads.append(threading.Thread(target=install_host, args=('192.168.111.10', 'host0', 'test', 'test', True)))
threads.append(threading.Thread(target=install_host, args=('192.168.111.11', 'host1', 'test', 'test', True)))
threads.append(threading.Thread(target=install_host, args=('192.168.111.12', 'host2', 'test', 'test', True)))
threads.append(threading.Thread(target=install_host, args=('192.168.111.13', 'host3', 'test', 'test', True)))
for t in threads:
    t.start()
for t in threads:
    t.join()

# Find LUN ids:
host0 = api.hosts.get('host0')
login_action = host0.iscsidiscover(
    action=params.Action(iscsi=params.IscsiDetails(address='192.168.111.3', port=3260),
                         async=False))
print login_action.iscsi_target
host0.iscsilogin(
    action=params.Action(iscsi=params.IscsiDetails(address='192.168.111.3',
                                                   target=login_action.iscsi_target[0]),
                         async=False))
luns_ids = [x.id for x in host0.storage.list()]
print luns_ids
t1 = threading.Thread(target=add_iscsi_storage,
                      args=('192.168.111.3', 'iqn.2014-07.org.ovirt:storage',
                            luns_ids, 'iscsi', 'host0', 'test'))
t2 = threading.Thread(target=add_nfs_storage,
                      args=('192.168.111.4', '/exports/nfs',
                            'nfs', 'host3', 'test'))
t1.start()
t1.join()
t2.start()
t2.join()
