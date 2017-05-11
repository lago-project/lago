from lago import subnet_lease
import pytest
import uuid
import os
import json
import shutil


def lease_has_valid_uuid(path_to_lease):
    with open(path_to_lease, mode='rt') as f:
        uuid_path, uuid_value = json.load(f)

    with open(uuid_path, mode='rt') as f:
        return uuid_value == f.read()


class PrefixMock(object):
    def __init__(self, path):
        self._path = path
        self._uuid_path = os.path.join(path, 'uuid')
        self._validate_path()
        self._create_uuid()

    def _validate_path(self):
        if not os.path.isdir(self.path):
            os.makedirs(self.path)

    def _create_uuid(self):
        with open(self.uuid_path, mode='wt') as f:
            f.write(uuid.uuid1().hex)

    def remove(self):
        shutil.rmtree(self.path)

    @property
    def path(self):
        return self._path

    @property
    def uuid_path(self):
        return self._uuid_path


class TestSubnetStore(object):
    def create_prefixes(self, path_to_workdir, num_of_prefixes=2):
        prefixes = []
        for i in range(0, num_of_prefixes):
            prefix_path = os.path.join(path_to_workdir, 'prefix_{}'.format(i))
            prefixes.append(PrefixMock(prefix_path))

        return prefixes

    def create_workdir_with_prefixes(self, temp_dir, num_of_prefixes=2):
        workdir = temp_dir.mkdir('workdir')
        return self.create_prefixes(str(workdir), num_of_prefixes)

    @pytest.fixture()
    def subnet_store(self, tmpdir):
        subnet_store_path = tmpdir.mkdir('subnet_store')
        return subnet_lease.SubnetStore(str(subnet_store_path))

    @pytest.fixture()
    def prefixes(self, tmpdir):
        return self.create_workdir_with_prefixes(tmpdir)

    @pytest.fixture()
    def prefix(self, tmpdir):
        return \
            self.create_workdir_with_prefixes(tmpdir, num_of_prefixes=1)[0]

    @pytest.mark.parametrize('subnet', [None, '192.168.210.0'])
    def test_take_random_lease(self, subnet_store, subnet, prefix):
        network = subnet_store.acquire(prefix.uuid_path, subnet)
        third_octet = str(network).split('.')[2]
        path_to_lease = os.path.join(
            subnet_store.path, '{}.lease'.format(third_octet)
        )
        _, dirnames, filenames = os.walk(subnet_store.path).next()
        assert \
            len(dirnames) == 0 and \
            len(filenames) == 1 and \
            lease_has_valid_uuid(path_to_lease)

    @pytest.mark.parametrize('subnet', ['127.0.0.1', '10.10.10.0'])
    def test_fail_on_out_of_range_subnet(self, subnet_store, subnet, prefix):
        with pytest.raises(subnet_lease.LagoSubnetLeaseOutOfRangeException):
            subnet_store.acquire(prefix.uuid_path, subnet)

    @pytest.mark.parametrize('subnet', ['256.256.256.56', '0.0.0.-1'])
    def test_fail_on_malformed_address(self, subnet_store, subnet, prefix):
        with pytest.raises(subnet_lease.LagoSubnetLeaseMalformedAddrException):
            subnet_store.acquire(prefix.uuid_path, subnet)

    def test_fail_on_full_store(self, subnet_store, prefix):
        for i in xrange(
            subnet_store._min_third_octet, subnet_store._max_third_octet + 1
        ):
            subnet_store.acquire(prefix.uuid_path)

        with pytest.raises(subnet_lease.LagoSubnetLeaseStoreFullException):
            subnet_store.acquire(prefix.uuid_path)

    def test_recalim_lease(self, subnet_store, prefix):
        network = subnet_store.acquire(prefix.uuid_path)
        reclaimed_network = subnet_store.acquire(
            prefix.uuid_path, str(network)
        )

        assert network == reclaimed_network

    def test_fail_to_calim_taken_lease(self, subnet_store, prefixes):
        with pytest.raises(subnet_lease.LagoSubnetLeaseTakenException):
            network = subnet_store.acquire(prefixes[0].uuid_path)
            subnet_store.acquire(prefixes[1].uuid_path, str(network))

    def test_take_stale_lease(self, subnet_store, prefixes):
        network = subnet_store.acquire(prefixes[0].uuid_path)
        prefixes[0].remove()
        subnet_store.acquire(prefixes[1].uuid_path, str(network))
