import pytest
import mock
import lago
from utils import generate_workdir_props


@pytest.fixture()
def mock_workdir(tmpdir, **kwargs):
    default_props = generate_workdir_props(**kwargs)
    return mock.Mock(
        spec_set=lago.workdir.Workdir(str(tmpdir)), **default_props
    )


@pytest.fixture
def empty_prefix():
    return lago.prefix.Prefix(prefix='')
