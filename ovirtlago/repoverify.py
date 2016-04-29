#
# Copyright 2014 Red Hat, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA
#
# Refer to the README and COPYING files for full details of the license
#
"""
This module contains all the functions related to syncing yum repos, it also
defines the format for the reposync configuration file.


Reposync config file
---------------------------
In order to provide fast package installation to the vms lago creates a local
repository for each prefix, right now is also the only way to pass local repos
to the vms too.

This file should be a valid yum config file, with the repos that you want to
be available for the vms declared there with a small extension, the whitelist
and blacklist options:

Include
++++++++++
For each repo you can define an option 'include' with a space separated list
of :mod:`fnmatch` patterns to allow only rpms that match them

Exclude
++++++++++
Similar to include, you can define an option 'exclude' with a space separated
list of :mod:`fnmatch` patterns to ignore any rpms that match them


Example::

    [main]
    reposdir=/etc/reposync.repos.d

    [local-vdsm-build-el7]
    name=VDSM local built rpms
    baseurl=file:///home/dcaro/Work/redhat/ovirt/vdsm/exported-artifacts
    enabled=1
    gpgcheck=0

    [ovirt-master-snapshot-el7]
    name=oVirt Master Nightly Test Releases
    baseurl=http://resources.ovirt.org/pub/ovirt-master-snapshot/rpm/el7/
    exclude=vdsm-* ovirt-node-* *-debuginfo ovirt-engine-appliance
    enabled=1
    gpgcheck=0


"""
import ConfigParser
import fnmatch
import functools
import gzip
import logging
import os
import StringIO
import urllib2

import lxml.etree
import rpmUtils.arch
import rpmUtils.miscutils

import lago.utils
from lago import log_utils

LOGGER = logging.getLogger(__name__)
LogTask = functools.partial(log_utils.LogTask, logger=LOGGER)
log_task = functools.partial(log_utils.log_task, logger=LOGGER)


def gen_to_list(func):
    """
    Decorator to wrap the results of the decorated function in a list
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return list(func(*args, **kwargs))

    return wrapper

#: Randomly chosen rpm xml name spaces (I swear, we used a dice)
RPMNS = {
    'rpm': 'http://linux.duke.edu/metadata/repo',
    'common': 'http://linux.duke.edu/metadata/common'
}


def fetch_xml(url):
    """
    Retrieves an xml resource from a url

    Args:
        url (str): URL to get the xml from

    Returns:
        lxml.etree._Element: Root of the xml tree for the retrieved resource
    """
    content = urllib2.urlopen(url).read()

    if url.endswith('.gz'):
        content = gzip.GzipFile(fileobj=StringIO.StringIO(content)).read()

    return lxml.etree.fromstring(content)


def _pkg_in_pattern_list(pattern_list, pkg):
    return (
        pkg in pattern_list or any(
            fnmatch.fnmatch(pkg, pat) for pat in pattern_list
        )
    )


def _passes_whitelist(whitelist, rpm_string, rpm_name):
    return (
        whitelist and (
            _pkg_in_pattern_list(whitelist, rpm_string)
            or _pkg_in_pattern_list(whitelist, rpm_name)
        ) or not whitelist
    )


def _passes_blacklist(blacklist, rpm_string, rpm_name):
    return (
        blacklist and not (
            _pkg_in_pattern_list(blacklist, rpm_string) or
            _pkg_in_pattern_list(blacklist, rpm_name)
        ) or not blacklist
    )


def _passes_lists(whitelist, blacklist, rpm_string, rpm_name):
    if (
        _passes_whitelist(whitelist, rpm_string, rpm_name)
        and _passes_blacklist(blacklist, rpm_string, rpm_name)
    ):
        return True

    return False


def _get_packages_from_repo_url(repo_url):
    repomd_url = '%s/repodata/repomd.xml' % repo_url
    repomd_xml = fetch_xml(repomd_url)
    primary_xml_loc = repomd_xml.xpath(
        '/rpm:repomd/rpm:data[@type="primary"]/rpm:location',
        namespaces=RPMNS,
    )[0].attrib['href']
    primary_xml = fetch_xml('%s/%s' % (repo_url, primary_xml_loc))
    return primary_xml.xpath(
        '/common:metadata/common:package[@type="rpm"]',
        namespaces=RPMNS,
    )


def get_packages(repo_url, whitelist=None, blacklist=None, only_latest=True):
    """
    Retrieves the package info from the given repo, filtering with whitelist
    and blacklist

    Args:
        repo_url (str): URL to the repo to ger rpm info from
        whitelist (list of str): :mod:`fnmatch` patterns to whitelist by
        blacklist (list of str): :mod:`fnmatch` patterns to blacklist by

    Returns:
        list of dict: list with the rpm info for each rpm that passed the
        filters, where the returned dict has the keys:

            * name (str): Name of the rpm
            * location (str): URL for the rpm, relative to the repo url
            * checksum (dict): dict with the hash type and value
                * checksum[type] (str): type of checksum (usually sha256)
                * checksum[hash] (str): value for the checksum
            * build_time (int): Time when the package was built
            * version (tuple of str, str, str): tuple with the epoc, version
              and release strings for that rpm


    Warning:
        The whitelist is actually doing the same as blacklist, **the example
        below shows what it shoud do, not what it does**

    Example:

        >>> get_packages(
        ...    'http://resources.ovirt.org/pub/ovirt-master-snapshot/rpm/el7/',
        ...    whitelist=['*ioprocess*'],
        ...    blacklist=['*debuginfo*'],
        ... )
        ... # doctest: +ELLIPSIS
        [{'build_time': 1...,
            'checksum': {'hash': '...',
            'type': 'sha256'},
            'location': 'noarch/python-ioprocess-....el7.noarch.rpm',
            'name': 'python-ioprocess',
            'version': ('...', '...', '....el7')},
        {'build_time': 1...,
            'checksum': {'hash': '...',
            'type': 'sha256'},
            'location': 'noarch/python-ioprocess-....el7.noarch.rpm',
            'name': 'python-ioprocess',
            'version': ('...', '...', '....el7')},
        {'build_time': 1...,
            'checksum': {'hash': '...',
            'type': 'sha256'},
            'location': 'x86_64/ioprocess-....el7.x86_64.rpm',
            'name': 'ioprocess',
            'version': ('0', '0.15.0', '3.el7')},
        {'build_time': 1...,
            'checksum': {'hash': '...',
            'type': 'sha256'},
            'location': 'x86_64/ioprocess-....el7.x86_64.rpm',
            'name': 'ioprocess',
            'version': ('...', '...', '....el7')}]


    """
    available_arches = rpmUtils.arch.getArchList()
    rpms_by_name = {}
    unfiltered_packages = _get_packages_from_repo_url(repo_url=repo_url)
    LOGGER.debug(
        'Got %d unfiltered packages from %s',
        len(unfiltered_packages),
        repo_url,
    )
    for pkg_element in unfiltered_packages:
        name = pkg_element.xpath('common:name', namespaces=RPMNS)[0].text
        arch = pkg_element.xpath('common:arch', namespaces=RPMNS)[0].text
        if arch not in available_arches:
            continue

        rpm = {
            'name': name,
            'location': pkg_element.xpath(
                'common:location',
                namespaces=RPMNS,
            )[0].attrib['href'],
            'checksum': {
                'type': pkg_element.xpath(
                    'common:checksum',
                    namespaces=RPMNS,
                )[0].attrib['type'],
                'hash': pkg_element.xpath(
                    'common:checksum',
                    namespaces=RPMNS,
                )[0].text,
            },
            'version': (
                pkg_element.xpath(
                    'common:version',
                    namespaces=RPMNS,
                )[0].attrib['epoch'],
                pkg_element.xpath(
                    'common:version',
                    namespaces=RPMNS,
                )[0].attrib['ver'],
                pkg_element.xpath(
                    'common:version',
                    namespaces=RPMNS,
                )[0].attrib['rel'],
            ),
            'build_time': int(
                pkg_element.xpath(
                    'common:time',
                    namespaces=RPMNS,
                )[0].attrib['build']
            ),
            'arch': arch,
        }

        if not _passes_lists(
            whitelist=whitelist,
            blacklist=blacklist,
            rpm_string='%s-%s.%s' % (
                rpm['name'], '%s.%s' % rpm['version'][1:], rpm['arch']
            ),
            rpm_name=rpm['name'],
        ):
            continue

        if rpm['location'].endswith('.src.rpm'):
            name = 'src-%s' % name

        if (
            name not in rpms_by_name or rpmUtils.miscutils.compareEVR(
                rpms_by_name[name]['version'], rpm['version']
            ) < 0
        ):
            rpms_by_name[name] = rpm
        else:
            continue

    return rpms_by_name.values()


def verify_repo(repo_url, path, whitelist=None, blacklist=None):
    """
    Verifies that the given repo url is properly synced to the given path

    Args:
        repo_url (str): Remote URL to sync locally
        path (str): Local path to sync to
        whitelist (list of str): List of patterns to whitelist by
        blacklist (list of str): List of patterns to blacklist by

    Returns:
        None

    Raises:
        RuntimeError: if there's a local rpm that does not exist in the remote
            repo url

    See Also:
        :func:`get_packages`
    """
    downloaded_rpms = []
    whitelist = whitelist or {'*': True}
    blacklist = blacklist or {}
    for _, _, files in os.walk(path):
        downloaded_rpms.extend(
            fname for fname in files if fname.endswith('.rpm')
        )
    packages = get_packages(repo_url, whitelist, blacklist, only_latest=True)
    LOGGER.debug(
        'Got %d filtered packages for repo %s',
        len(packages),
        repo_url,
    )

    are_there_missing_rpms = False
    for rpm in get_packages(repo_url, whitelist, blacklist, only_latest=True):
        rpm_filename = os.path.basename(rpm['location'])

        if rpm_filename.endswith('.src.rpm'):
            continue

        if rpm_filename not in downloaded_rpms:
            are_there_missing_rpms = True
            LOGGER.error(
                'RPM %s from %s is missing locally ',
                rpm['name'],
                repo_url,
            )

    if are_there_missing_rpms:
        raise RuntimeError(
            'Some rpms were not found locally for repo %s' % repo_url
        )


def verify_reposync(config_path, sync_dir, repo_whitelist=None):
    """
    Verifies that the given reposync configuration is properly updated in the
    given sync dir, skipping any non-whitelisted repos

    Args:
        config_path (str): Path to the reposync configuration file
        sync_dir (str): Local path to the parent dir where to look for the
            repos, if not there, they will get created
        repo_whitelist (list of str): list with the :mod:`fnmatch` patterns to
            whitelist repos by, if empty or not passed, it will not filter the
            repos

    Returns:
        None
    """
    config = ConfigParser.SafeConfigParser()
    with open(config_path) as config_fd:
        config.readfp(config_fd)

    verify_repo_jobs = []
    for repo in config.sections():
        if repo == 'main':
            continue

        if repo_whitelist and repo not in repo_whitelist:
            continue

        if not config.getint(repo, 'enabled'):
            continue

        if config.has_option(repo, 'includepkgs'):
            # a dict is a couple orders of magnitude faster than a list
            whitelist = {
                pkg: True
                for pkg in config.get(repo, 'includepkgs').split(' ')
            }
        else:
            whitelist = None

        if config.has_option(repo, 'exclude'):
            # a dict is a couple orders of magnitude faster than a list
            blacklist = {
                pkg: True
                for pkg in config.get(repo, 'exclude').split(' ')
            }
        else:
            blacklist = None

        repo_path = os.path.join(sync_dir, repo)

        def _verify_repo_job(base_url, *args, **kwargs):
            with LogTask('Verifying repo %s' % base_url):
                verify_repo(base_url, *args, **kwargs)

        verify_repo_jobs.append(
            functools.partial(
                _verify_repo_job,
                config.get(repo, 'baseurl'),
                repo_path,
                whitelist,
                blacklist,
            )
        )
    lago.utils.invoke_in_parallel(lambda f: f(), verify_repo_jobs)
