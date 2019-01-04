# encoding: utf-8
"""
This module contains any disk template related classes and functions, including
the repository store manager classes and template providers, some useful
definitions:

    * Template repositories:
        Repository where to fetch templates from, as an http server

    * Template store:
        Local store to cache templates

    * Template:
        Unititialized disk image to use as base for other disk images

    * Template version:
        Specific version of a template, to allow getting updates without
        having to change the template name everywhere

"""
import errno
import json
import logging
import os
import posixpath
import shutil
import urllib
import sys

import utils
from . import log_utils
from .config import config

from future.builtins import super

LOGGER = logging.getLogger(__name__)


class FileSystemTemplateProvider:
    """
    Handles file type templates, that is, getting a disk template from the
    host's filesystem
    """

    def __init__(self, root):
        """
        Args:
            root (str): Path to the template, any vars and user globs wil be
                expanded
        """
        self._root = os.path.expanduser(os.path.expandvars(root))

    def _prefixed(self, *path):
        """
        Join all the given paths prefixed with this provider's base root path

        Args:
            *path (str): sections of the path to join, passed as positional
                arguments

        Returns:
            str: Joined paths prepended with the provider root path
        """
        return os.path.join(self._root, *path)

    def download_image(self, handle, dest):
        """
        Copies over the handl to the destination

        Args:
            handle (str): path to copy over
            dest (str): path to copy to

        Returns:
            None
        """
        shutil.copyfile(self._prefixed(handle), dest)

    def get_hash(self, handle):
        """
        Returns the associated hash for the given handle, the hash file must
        exist (``handle + '.hash'``).

        Args:
            handle (str): Path to the template to get the hash from

        Returns:
            str: Hash for the given handle
        """
        handle = os.path.expanduser(os.path.expandvars(handle))
        with open(self._prefixed('%s.hash' % handle)) as f:
            return f.read()

    def get_metadata(self, handle):
        """
        Returns the associated metadata info for the given handle, the metadata
        file must exist (``handle + '.metadata'``).

        Args:
            handle (str): Path to the template to get the metadata from

        Returns:
            dict: Metadata for the given handle
        """
        handle = os.path.expanduser(os.path.expandvars(handle))
        with open(self._prefixed('%s.metadata' % handle)) as f:
            return json.load(f)


class HttpTemplateProvider:
    """
    This provider allows the usage of http urls for templates
    """

    def __init__(self, baseurl):
        """
        Args:
           baseurl (str): Url to prepend to every handle
        """
        self.baseurl = baseurl

    def open_url(self, url, suffix='', dest=None):
        """
        Opens the given url, trying the compressed version first.
        The compressed version url is generated adding the ``.xz`` extension
        to the ``url`` and adding the given suffix **after** that ``.xz``
        extension.
        If dest passed, it will download the data to that path if able

        Args:
            url (str): relative url from the ``self.baseurl`` to retrieve
            suffix (str): optional suffix to append to the url after adding
                the compressed extension to the path
            dest (str or None): Path to save the data to

        Returns:
            urllib.addinfourl: response object to read from (lazy read), closed
                if no dest passed

        Raises:
            RuntimeError: if the url gave http error when retrieving it
        """
        if not url.endswith('.xz'):
            try:
                return self.open_url(
                    url=url + '.xz',
                    suffix=suffix,
                    dest=dest,
                )
            except RuntimeError:
                pass
        full_url = posixpath.join(self.baseurl, url) + suffix
        response = urllib.urlopen(full_url)
        if response.code >= 300:
            raise RuntimeError(
                'Failed no retrieve URL %s:\nCode: %d' %
                (full_url, response.code)
            )

        meta = response.info()
        file_size_kb = int(meta.getheaders("Content-Length")[0]) / 1024
        if file_size_kb > 0:
            sys.stdout.write(
                "Downloading %s Kilobytes from %s \n" %
                (file_size_kb, full_url)
            )

        def report(count, block_size, total_size):
            percent = (count * block_size * 100 / float(total_size))
            sys.stdout.write(
                "\r% 3.1f%%" % percent + " complete (%d " %
                (count * block_size / 1024) + "Kilobytes)"
            )
            sys.stdout.flush()

        if dest:
            response.close()
            urllib.urlretrieve(full_url, dest, report)
            sys.stdout.write("\n")
        return response

    def download_image(self, handle, dest):
        """
        Downloads the image from the http server

        Args:
            handle (str): url from the `self.baseurl` to the remote template
            dest (str): Path to store the downloaded url to, must be a file
                path

        Returns:
            None
        """
        with log_utils.LogTask('Download image %s' % handle, logger=LOGGER):
            self.open_url(url=handle, dest=dest)

        self.extract_image_xz(dest)

    @staticmethod
    def extract_image_xz(path):
        if not path.endswith('.xz'):
            os.rename(path, path + '.xz')
            path = path + '.xz'

        with log_utils.LogTask('Decompress local image', logger=LOGGER):
            ret = utils.run_command(
                ['xz', '--threads=0', '--decompress', path],
            )

        if ret:
            raise RuntimeError('Failed to decompress %s' % path)

    def get_hash(self, handle):
        """
        Get the associated hash for the given handle, the hash file must
        exist (``handle + '.hash'``).

        Args:
            handle (str): Path to the template to get the hash from

        Returns:
            str: Hash for the given handle
        """
        response = self.open_url(url=handle, suffix='.hash')
        try:
            return response.read()
        finally:
            response.close()

    def get_metadata(self, handle):
        """
        Returns the associated metadata info for the given handle, the metadata
        file must exist (``handle + '.metadata'``). If the given handle has an
        ``.xz`` extension, it will get removed when calculating the handle
        metadata path

        Args:
            handle (str): Path to the template to get the metadata from

        Returns:
            dict: Metadata for the given handle
        """
        response = self.open_url(url=handle, suffix='.metadata')
        try:
            return json.load(response)
        finally:
            response.close()


#: Registry for template providers
_PROVIDERS = {
    'file': FileSystemTemplateProvider,
    'http': HttpTemplateProvider,
}


def find_repo_by_name(name, repo_dir=None):
    """
    Searches the given repo name inside the repo_dir (will use the config value
    'template_repos' if no repo dir passed), will rise an exception if not
    found

    Args:
        name (str): Name of the repo to search
        repo_dir (str): Directory where to search the repo

    Return:
        str: path to the repo

    Raises:
        RuntimeError: if not found
    """
    if repo_dir is None:
        repo_dir = config.get('template_repos')

    ret, out, _ = utils.run_command([
        'find',
        repo_dir,
        '-name',
        '*.json',
    ], )

    repos = [
        TemplateRepository.from_url(line.strip()) for line in out.split('\n')
        if len(line.strip())
    ]

    for repo in repos:
        if repo.name == name:
            return repo
    raise RuntimeError('Could not find repo %s' % name)


class TemplateRepository:
    """
    A template repository is a single source for templates, that uses different
    providers to actually retrieve them. That means for example that the
    'ovirt' template repository, could support the 'http' and a theoretical
    'gluster' template providers.


    Attributes:
        _dom (dict): Specification of the template
        _providers (dict): Providers instances for any source in the spec
    """

    def __init__(self, dom, path):
        """
        You would usually use the
        :func:`TemplateRepository.from_url` method instead of
        directly using this

        Args:
            dom (dict): Specification of the template repository (not confuse
                with xml dom)
        """
        self._dom = dom
        self._providers = {
            name: self._get_provider(spec)
            for name, spec in self._dom.get('sources', {}).items()
        }
        self._path = path

    @classmethod
    def from_url(cls, path):
        """
        Instantiate a :class:`TemplateRepository` instance from the data in a
        file or url

        Args:
            path (str): Path or url to the json file to load

        Returns:
            TemplateRepository: A new instance
        """
        if os.path.isfile(path):
            with open(path) as fd:
                data = fd.read()
        else:
            try:
                response = urllib.urlopen(path)
                if response.code >= 300:
                    raise RuntimeError('Unable to load repo from %s' % path)

                data = response.read()
                response.close()
            except IOError:
                raise RuntimeError(
                    'Unable to load repo from %s (IO error)' % path
                )

        return cls(json.loads(data), path)

    def _get_provider(self, spec):
        """
        Get the provider for the given template spec

        Args:
            spec (dict): Template spec

        Returns:
            HttpTemplateProvider or FileSystemTemplateProvider:
                A provider instance for that spec
        """
        provider_class = _PROVIDERS[spec['type']]
        return provider_class(**spec['args'])

    @property
    def name(self):
        """
        Getter for the template repo name

        Returns:
            str: the name of this template repo
        """
        return self._dom['name']

    @property
    def path(self):
        """
        Getter for the template repo path

        Returns:
            str: the path/url of this template repo
        """
        return self._path

    def get_by_name(self, name):
        """
        Retrieve a template by it's name

        Args:
            name (str): Name of the template to retrieve

        Raises:
            LagoMissingTemplateError: if no template is found
        """
        try:
            spec = self._dom.get('templates', {})[name]
        except KeyError:
            raise LagoMissingTemplateError(name, self._path)

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
    """
    Disk image template class

    Attributes:
        name (str): Name of this template
        _versions (dict(str:TemplateVersion)): versions for this template
    """

    def __init__(self, name, versions):
        """
        Args:
            name (str): Name of the template
            versions (dict(str:TemplateVersion)): dictionary with the
                version_name: :class:`TemplateVersion` pairs for this template
        """
        self.name = name
        self._versions = versions

    def get_version(self, ver_name=None):
        """
        Get the given version for this template, or the latest

        Args:
            ver_name (str or None): Version to retieve, None for the latest

        Returns:
            TemplateVersion: The version matching the given name or the latest
                one
        """
        if ver_name is None:
            return self.get_latest_version()
        return self._versions[ver_name]

    def get_latest_version(self):
        """
        Retrieves the latest version for this template, the latest being the
        one with the newest timestamp

        Returns:
            TemplateVersion
        """
        return max(self._versions.values(), key=lambda x: x.timestamp())


class TemplateVersion:
    """
    Each template can have multiple versions, each of those is actually a
    different disk template file representation, under the same base name.
    """

    def __init__(self, name, source, handle, timestamp):
        """

        Args:
            name (str): Base name of the template
            source (HttpTemplateProvider or FileSystemTemplateProvider):
                template provider for this version
            handle (str): handle of the template version, this is the
                information that will be used passed to the repo provider to
                retrieve the template (depends on the provider)
            timestamp (int): timestamp as seconds since 1970-01-01 00:00:00
                UTC
        """
        self.name = name
        self._source = source
        self._handle = handle
        self._timestamp = timestamp
        self._hash = None
        self._metadata = None

    def timestamp(self):
        """
        Getter for the timestamp
        """
        return self._timestamp

    def get_hash(self):
        """
        Returns the associated hash for this template version

        Returns:
            str: Hash for this version
        """
        if self._hash is None:
            self._hash = self._source.get_hash(self._handle).strip()
        return self._hash

    def get_metadata(self):
        """
        Returns the associated metadata info for this template version

        Returns:
            dict: Metadata for this version
        """

        if self._metadata is None:
            self._metadata = self._source.get_metadata(self._handle)
        return self._metadata

    def download(self, destination):
        """
        Retrieves this template to the destination file

        Args:
            destination (str): file path to write this template to

        Returns:
            None
        """
        self._source.download_image(self._handle, destination)


class TemplateStore:
    """
    Local cache to store templates

    The store uses various files to keep track of the templates cached, access
    and versions. An example template store looks like::

        $ tree /var/lib/lago/store/
        /var/lib/lago/store/
        ├── in_office_repo:centos6_engine:v2.tmp
        ├── in_office_repo:centos7_engine:v5.tmp
        ├── in_office_repo:fedora22_host:v2.tmp
        ├── phx_repo:centos6_engine:v2
        ├── phx_repo:centos6_engine:v2.hash
        ├── phx_repo:centos6_engine:v2.metadata
        ├── phx_repo:centos6_engine:v2.users
        ├── phx_repo:centos7_engine:v4.tmp
        ├── phx_repo:centos7_host:v4.tmp
        └── phx_repo:storage-nfs:v1.tmp

    There you can see the files:

    * \*.tmp
        Temporary file created while downloading the template from the
        repository (depends on the provider)

    * ${repo_name}:${template_name}:${template_version}
        This file is the actual disk image template

    * \*.hash
        Cached hash for the template disk image

    * \*.metadata
        Metadata for this template image in json format, usually this includes
        the `distro` and `root-password`
    """

    def __init__(self, path):
        """
        :param str path: Path to a local dir for this store, will be created if
            it does not exist
        :raises OSError: if there's a failure creating the dir
        """
        self._root = path
        try:
            os.makedirs(path)
        except OSError as e:
            if e.errno != errno.EEXIST:
                LOGGER.error('Failed to create store dir')
                raise

    def _prefixed(self, *path):
        """
        Join the given paths and prepend this stores path

        Args:
            *path (str): list of paths to join, as positional arguments

        Returns:
            str: all the paths joined and prepended with the store path
        """
        return os.path.join(self._root, *path)

    def __contains__(self, temp_ver):
        """
        Checks if a given version is in this store

        Args:
            temp_ver (TemplateVersion): Version to look for

        Returns:
            bool: ``True`` if the version is in this store
        """
        return os.path.exists(self._prefixed(temp_ver.name))

    def get_path(self, temp_ver):
        """
        Get the path of the given version in this store

        Args:
            temp_ver TemplateVersion: version to look for

        Returns:
            str: The path to the template version inside the store

        Raises:
            RuntimeError: if the template is not in the store
        """
        if temp_ver not in self:
            raise RuntimeError(
                'Template: {} not present'.format(temp_ver.name)
            )
        return self._prefixed(temp_ver.name)

    def download(self, temp_ver, store_metadata=True):
        """
        Retrieve the given template version

        Args:
            temp_ver (TemplateVersion): template version to retrieve
            store_metadata (bool): If set to ``False``, will not refresh the
                local metadata with the retrieved one

        Returns:
            None
        """
        dest = self._prefixed(temp_ver.name)
        temp_dest = '%s.tmp' % dest

        with utils.LockFile(dest + '.lock'):
            # Image was downloaded while we were waiting
            if os.path.exists(dest):
                return

            temp_ver.download(temp_dest)
            if store_metadata:
                with open('%s.metadata' % dest, 'w') as f:
                    utils.json_dump(temp_ver.get_metadata(), f)

            sha1 = utils.get_hash(temp_dest)
            if temp_ver.get_hash() != sha1:
                raise RuntimeError(
                    'Image %s does not match the expected hash %s' % (
                        temp_ver.name,
                        sha1,
                    )
                )

            with open('%s.hash' % dest, 'w') as f:
                f.write(sha1)

            with log_utils.LogTask('Convert image', logger=LOGGER):
                result = utils.run_command(
                    [
                        'qemu-img',
                        'convert',
                        '-O',
                        'raw',
                        temp_dest,
                        dest,
                    ],
                )

                os.unlink(temp_dest)
                if result:
                    raise RuntimeError(result.err)

    def get_stored_metadata(self, temp_ver):
        """
        Retrieves the metadata for the given template version from the store

        Args:
            temp_ver (TemplateVersion): template version to retrieve the
                metadata for

        Returns:
            dict: the metadata of the given template version
        """
        with open(self._prefixed('%s.metadata' % temp_ver.name)) as f:
            return json.load(f)

    def get_stored_hash(self, temp_ver):
        """
        Retrieves the hash for the given template version from the store

        Args:
            temp_ver (TemplateVersion): template version to retrieve the hash
                for

        Returns:
            str: hash of the given template version
        """
        with open(self._prefixed('%s.hash' % temp_ver.name)) as f:
            return f.read().strip()


class LagoMissingTemplateError(utils.LagoException):
    def __init__(self, name, path):
        super().__init__(
            'Image {} doesn\'t exist in repo {}'.format(name, path)
        )
