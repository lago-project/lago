import pytest
from pytest import fixture
from lago import sysprep
import jinja2
import os


class TemplateFactory(object):
    def __init__(self, dst):
        self.dst = dst
        self.loader = jinja2.FileSystemLoader(dst)

    def add(self, name, content):
        path = os.path.join(self.dst, name)
        with open(path, 'w+') as template:
            template.write(content)

    def add_base(self, content):
        self.add(content=content, name='sysprep-base.j2')


@fixture
def factory(tmpdir):
    return TemplateFactory(dst=str(tmpdir))


class TestSysprep(object):
    @pytest.mark.parametrize(
        'distro,templates,expected', [
            ('distro_a', ['base'], 'base'),
            ('distro_a', ['base', 'distro_a'], 'distro_a'),
            ('distro_b', ['base', 'distro_a'], 'base')
        ]
    )
    def test_render_template_loads_expected(
        self, factory, distro, templates, expected
    ):
        for template in templates:
            factory.add('sysprep-{0}.j2'.format(template), 'empty template')
        filename = sysprep._render_template(
            distro=distro, loader=factory.loader
        )

        with open(filename, 'r') as generated:
            lines = [line.strip() for line in generated.readlines()]
        assert lines[0].strip() == '# sysprep-{0}.j2'.format(expected)
        assert lines[1].strip() == 'empty template'

    def test_dedent_filter(self, factory):
        template = '{{ var|dedent }}'
        factory.add_base(template)
        filename = sysprep._render_template(
            distro='base', loader=factory.loader, var='\tremove-indent'
        )

        with open(filename, 'r') as generated:
            lines = generated.readlines()
        assert lines[0].strip() == '# sysprep-base.j2'
        assert lines[1] == 'remove-indent'
