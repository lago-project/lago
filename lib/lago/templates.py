import errno
import functools
import hashlib
import json
import os
import shutil
import time
import urllib

import lockfile

import config
import utils


class FileSystemTemplateProvider:
    def __init__(self, root):
        self._root = os.path.expanduser(os.path.expandvars(root))

    def _prefixed(self, *path):
        return os.path.join(self._root, *path)

    def download_image(self, handle, dest):
        shutil.copyfile(self._prefixed(handle), dest)

    def get_hash(self, handle):
        handle = os.path.expanduser(os.path.expandvars(handle))
        with open(self._prefixed('%s.hash' % handle)) as f:
            return f.read()

    def get_metadata(self, handle):
        handle = os.path.expanduser(os.path.expandvars(handle))
        with open(self._prefixed('%s.metadata' % handle)) as f:
            return json.load(f)


class HttpTemplateProvider:
    def __init__(self, baseurl):
        self._baseurl = baseurl

    def download_image(self, handle, dest):
        urllib.urlretrieve(self._baseurl + handle, dest)

    def get_hash(self, handle):
        f = urllib.urlopen(self._baseurl + handle + '.hash')
        try:
            return f.read()
        finally:
            f.close()

    def get_metadata(self, handle):
        f = urllib.urlopen(self._baseurl + handle + '.metadata')
        try:
            return json.load(f)
        finally:
            f.close()


_PROVIDERS = {
    'file': FileSystemTemplateProvider,
    'http': HttpTemplateProvider,
}


def find_repo_by_name(name, repo_dir=None):
    if repo_dir is None:
        repo_dir = config.get('template_repos')

    ret, out, _ = utils.run_command(
        [
            'find',
            repo_dir,
            '-name', '*.json',
        ],
    )

    repos = [
        TemplateRepository.from_file(line.strip())
        for line in out.split('\n')
        if len(line.strip())
    ]

    for repo in repos:
        if repo.name == name:
            return repo
    raise RuntimeError('Could not find repo %s' % (name))


class TemplateRepository:
    def __init__(self, dom):
        self._dom = dom
        self._providers = {
            name: self._get_provider(spec)
            for name, spec in self._dom.get('sources', {}).items()
        }

    @classmethod
    def from_file(clazz, path):
        with open(path) as f:
            return clazz(json.load(f))

    def _get_provider(self, spec):
        provider_class = _PROVIDERS[spec['type']]
        return provider_class(**spec['args'])

    @property
    def name(self):
        return self._dom['name']

    def get_by_name(self, name):
        spec = self._dom.get('templates', {})[name]
        return Template(
            name=name,
            versions={
                ver_name: TemplateVersion(
                    name='%s:%s:%s' % (self.name, name, ver_name),
                    source=self._providers[ver_spec['source']],
                    handle=ver_spec['handle'],
                    timestamp=ver_spec['timestamp'],
                )
                for ver_name, ver_spec in spec['versions'].items()
            },
        )


class Template:
    def __init__(self, name, versions):
        self.name = name
        self._versions = versions

    def get_version(self, ver_name=None):
        if ver_name is None:
            return self.get_latest_version()
        return self._versions[ver_name]

    def get_latest_version(self):
        return max(self._versions.values(), key=lambda x: x.timestamp())


class TemplateVersion:
    def __init__(self, name, source, handle, timestamp):
        self.name = name
        self._source = source
        self._handle = handle
        self._timestamp = timestamp
        self._hash = None
        self._metadata = None

    def timestamp(self):
        return self._timestamp

    def get_hash(self):
        if self._hash is None:
            self._hash = self._source.get_hash(self._handle).strip()
        return self._hash

    def get_metadata(self):
        if self._metadata is None:
            self._metadata = self._source.get_metadata(self._handle)
        return self._metadata

    def download(self, destination):
        self._source.download_image(self._handle, destination)


def _locked(func):
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        with lockfile.LockFile(self.lock_path()):
            return func(self, *args, **kwargs)


class TemplateStore:
    def __init__(self, path):
        self._root = path
        try:
            os.makedirs(path)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise

    def _prefixed(self, *path):
        return os.path.join(self._root, *path)

    def __contains__(self, temp_ver):
        return os.path.exists(self._prefixed(temp_ver.name))

    def get_path(self, temp_ver):
        if temp_ver not in self:
            raise RuntimeError('Template not present')
        return self._prefixed(temp_ver.name)

    def download(self, temp_ver, store_metadata=True):
        dest = self._prefixed(temp_ver.name)
        temp_dest = '%s.tmp' % dest

        with lockfile.LockFile(dest):
            # Image was downloaded while we were waiting
            if os.path.exists(dest):
                return

            temp_ver.download(temp_dest)
            if store_metadata:
                with open('%s.metadata' % dest, 'w') as f:
                    utils.json_dump(temp_ver.get_metadata(), f)

            sha1 = hashlib.sha1()
            with open(temp_dest) as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    sha1.update(chunk)
            if temp_ver.get_hash() != sha1.hexdigest():
                raise RuntimeError(
                    'Image %s does not match the expected hash %s' % (
                        temp_ver.name,
                        sha1.hexdigest(),
                    )
                )

            with open('%s.hash' % dest, 'w') as f:
                f.write(sha1.hexdigest())

            utils.run_command(
                [
                    'qemu-img',
                    'convert',
                    '-O', 'raw',
                    temp_dest,
                    dest,
                ],
            )

            os.unlink(temp_dest)

            self._init_users(temp_ver)

    def _init_users(self, temp_ver):
        with open('%s.users' % self.get_path(temp_ver), 'w') as f:
            utils.json_dump(
                {
                    'users': {},
                    'last_access': int(time.time()),
                },
                f,
            )

    def get_stored_metadata(self, temp_ver):
        with open(self._prefixed('%s.metadata' % temp_ver.name)) as f:
            return json.load(f)

    def get_stored_hash(self, temp_ver):
        with open(self._prefixed('%s.hash' % temp_ver.name)) as f:
            return f.read().strip()

    def mark_used(self, temp_ver, key_path):
        dest = self.get_path(temp_ver)

        with lockfile.LockFile(dest):
            with open('%s.users' % dest) as f:
                users = json.load(f)

            updated_users = {}
            for path, key in users['users'].items():
                try:
                    with open(path) as f:
                        if key == f.read():
                            updated_users[path] = key
                except OSError:
                    pass
                except IOError:
                    pass

            with open(key_path) as f:
                updated_users[key_path] = f.read()
            users['users'] = updated_users
            users['last_access'] = int(time.time())
            with open('%s.users' % dest, 'w') as f:
                utils.json_dump(users, f)
