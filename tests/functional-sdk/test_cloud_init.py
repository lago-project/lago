import textwrap
import pytest
from jinja2 import BaseLoader, Environment
from textwrap import dedent
# from lago import sdk


@pytest.fixture(scope='module')
def images():
    """
    vm_name -> {template, do_bootstrap, cloud_init_config}
    """

    el7 = dedent(
        """
        cloud-init:
          user-data:
            write_files:
              - path: /root/test
                content: bla_bla_bla
        """
    )

    el7_no_bootstrap = dedent(
        """
        cloud-init:
          user-data:
            write_files:
              - path: /root/test
                content: bla_bla_bla
        """
    )

    # yapf: disable
    return {
        'el7': {
            'template': 'el7.4-base-2',
            'do_bootstrap': True,
            'cloud_init_config': el7
        },
        'el7-no-bootstrap': {
            'template': 'el7.4-base-2',
            'do_bootstrap': False,
            'cloud_init_config': el7_no_bootstrap
        }
    }
    # yapf: enable


@pytest.fixture(scope='module')
def init_str(images):
    init_template = textwrap.dedent(
        """
    domains:
      {% for vm_name, config in images.viewitems() %}
      {{ vm_name }}:
        bootstrap: {{ config.do_bootstrap }}
        {{ cloud_init_config }}
        memory: 1024
        nics:
          - net: net-01
        disks:
          - template_name: {{ config.template }}
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
      {% endfor %}

    nets:
      net-01:
        type: nat
        dhcp:
          start: 100
          end: 254
        management: true
        dns_domain_name: lago.local
    """
    )
    template = Environment(loader=BaseLoader()).from_string(init_template)
    return template.render(images=images)
