from lago import subnet_lease
from lago.subnet_lease import (
    LagoSubnetLeaseOutOfRangeException, LagoSubnetLeaseStoreFullException,
    LagoSubnetLeaseTakenException, LagoSubnetLeaseMalformedAddrException,
    LagoSubnetLeaseBadPermissionsException, LOCK_NAME
)

import pytest
import uuid
import os
import json
import shutil
import random
from mock import patch


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


@pytest.fixture
def prefix_mock_gen(tmpdir):
    def gen():
        while True:
            yield PrefixMock(path=str(tmpdir.mkdtemp(rootdir=str(tmpdir))))

    return gen


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
        _, dirnames, filenames = next(os.walk(subnet_store.path))

        try:
            # Don't count the lockfile
            filenames.remove(LOCK_NAME)
        except ValueError:
            pass

        assert \
            len(dirnames) == 0 and \
            len(filenames) == 1 and \
            lease_has_valid_uuid(path_to_lease)

    @pytest.mark.parametrize('subnet', ['127.0.0.1', '10.10.10.0'])
    def test_fail_on_out_of_range_subnet(self, subnet_store, subnet, prefix):
        with pytest.raises(LagoSubnetLeaseOutOfRangeException):
            subnet_store.acquire(prefix.uuid_path, subnet)

    @pytest.mark.parametrize('subnet', ['256.256.256.56', '0.0.0.-1'])
    def test_fail_on_malformed_address(self, subnet_store, subnet, prefix):
        with pytest.raises(LagoSubnetLeaseMalformedAddrException):
            subnet_store.acquire(prefix.uuid_path, subnet)

    def test_fail_on_full_store(self, subnet_store, prefix):
        for i in range(
            subnet_store._min_third_octet, subnet_store._max_third_octet + 1
        ):
            subnet_store.acquire(prefix.uuid_path)

        with pytest.raises(LagoSubnetLeaseStoreFullException):
            subnet_store.acquire(prefix.uuid_path)

    def test_recalim_lease(self, subnet_store, prefix):
        network = subnet_store.acquire(prefix.uuid_path)
        reclaimed_network = subnet_store.acquire(
            prefix.uuid_path, str(network)
        )

        assert network == reclaimed_network

    def test_fail_to_calim_taken_lease(self, subnet_store, prefixes):
        with pytest.raises(LagoSubnetLeaseTakenException):
            network = subnet_store.acquire(prefixes[0].uuid_path)
            subnet_store.acquire(prefixes[1].uuid_path, str(network))

    def test_take_stale_lease(self, subnet_store, prefixes):
        network = subnet_store.acquire(prefixes[0].uuid_path)
        prefixes[0].remove()
        subnet_store.acquire(prefixes[1].uuid_path, str(network))

    @pytest.mark.parametrize('num_prefixes', [7, 10, 55])
    @pytest.mark.parametrize('remains', [0, 3, 6])
    def test_release_several_prefixes(
        self, subnet_store, prefix_mock_gen, num_prefixes, remains
    ):
        def get_leases():
            return [f for f in os.listdir(subnet_store.path) if f != LOCK_NAME]

        gen = prefix_mock_gen()
        for _ in range(num_prefixes):
            subnet_store.acquire(next(gen).uuid_path)
        acquired = subnet_store.list_leases()
        assert all(lease.valid for lease in acquired)
        assert len(acquired) == num_prefixes
        assert len(get_leases()) == num_prefixes

        to_release = random.sample(acquired, num_prefixes - remains)
        subnet_store.release([lease.subnet for lease in to_release])

        assert len(subnet_store.list_leases()) == remains
        assert len(get_leases()) == remains

    def test_list_leases_raises(self, subnet_store):
        with patch('lago.subnet_lease.os.listdir') as mock_listdir:
            mock_listdir.side_effect = OSError(13, 'mocking orig'),
            with pytest.raises(
                LagoSubnetLeaseBadPermissionsException
            ) as excinfo:
                subnet_store.list_leases()
            assert mock_listdir.call_count == 1
            try:
                raise LagoSubnetLeaseBadPermissionsException(
                    store_path=subnet_store.path, prv_msg=None
                )
            except LagoSubnetLeaseBadPermissionsException as err:
                exp_begin = err.args[0]

            assert str(excinfo.value).startswith(exp_begin)
            assert str(excinfo.value).endswith('mocking orig')
