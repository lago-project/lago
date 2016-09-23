lago-install.yml playbook will setup a machine with lago and
ovirt-system-tests as noted down in the README.rst

To run it, set your hosts.ini with a lago section:

```ini
 [lago]
  my.lago.host
```

,and run the playbook:

```bash
ansible-playbook -i hosts.ini ansible/lago-install.yml
```
