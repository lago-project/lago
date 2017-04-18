from collections import OrderedDict
import lago.build as build
import pytest

fixtures_normalize_options = [
    ({}, []),
    (
        OrderedDict(
            [
                ('option0', 'arg0'),
                ('option1', 'arg1'),
                ('option2', 'arg2'),
            ]
        ), [
            '--option0',
            'arg0',
            '--option1',
            'arg1',
            '--option2',
            'arg2',
        ]
    ),
    (
        OrderedDict([
            ('a', 'arg0'),
            ('b', ''),
            ('option2', 'arg2'),
        ]), [
            '-a',
            'arg0',
            '-b',
            '--option2',
            'arg2',
        ]
    ),
]

fixtures_check_path_to_default_ssh_key = [
    [
        {
            'virt-customize': {
                'ssh-inject': '',
                'touch': '/root/dummy'
            }
        },
    ],
]

fixtures_test_normalize_build_spec_fail_on_missing_cmd = [
    [
        {
            'virt-customize': {
                'ssh-inject': '',
                'touch': '/root/dummy'
            }
        },
        {
            'unknown_cmd': {
                'option': 'arg'
            }
        },
    ],
]


class PathsMock(object):
    def ssh_id_rsa_pub(self):
        return '/root/.ssh/id_rsa.pub'


class TestBuild(object):
    @pytest.fixture()
    def paths(self):
        return PathsMock()

    @pytest.fixture()
    def builder(self, paths):
        return build.Build(
            name='dummy_builder',
            disk_path='/root/dummy_disk.qcow2',
            paths=paths
        )

    @pytest.mark.parametrize(
        'test_input, expected', fixtures_normalize_options
    )
    def test_normalize_options(self, test_input, expected):
        result = build.Build.normalize_options(test_input)
        assert result == expected

    @pytest.mark.parametrize(
        'build_spec', fixtures_test_normalize_build_spec_fail_on_missing_cmd
    )
    def test_normalize_build_spec_fail_on_missing_cmd(
        self, builder, build_spec
    ):
        with pytest.raises(build.BuildException):
            builder.normalize_build_spec(build_spec)

    @pytest.mark.parametrize(
        'build_spec', fixtures_check_path_to_default_ssh_key
    )
    def test_check_path_to_default_ssh_key(self, builder, build_spec, paths):
        builder.normalize_build_spec(build_spec)
        cmd = filter(lambda x: x.name == 'virt-customize', builder.build_cmds)
        expected = '--ssh-inject root:file:{}'.format(paths.ssh_id_rsa_pub())
        result = ' '.join(cmd.pop().cmd)
        assert expected in result
