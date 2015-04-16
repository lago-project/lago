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
import ConfigParser
import functools
import gzip
import os
import StringIO
import urllib2

import lxml.etree
import rpmUtils.arch
import rpmUtils.miscutils

import testenv.utils


def gen_to_list(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return list(func(*args, **kwargs))

    return wrapper

RPMNS = {
    'rpm': 'http://linux.duke.edu/metadata/repo',
    'common': 'http://linux.duke.edu/metadata/common'
}


def fetch_xml(url):
    content = urllib2.urlopen(url).read()

    if url.endswith('.gz'):
        content = gzip.GzipFile(fileobj=StringIO.StringIO(content)).read()

    return lxml.etree.fromstring(content)


@gen_to_list
def get_packages(repo_url, whitelist=None):
    repomd_url = '%s/repodata/repomd.xml' % repo_url
    repomd_xml = fetch_xml(repomd_url)
    primary_xml_loc = repomd_xml.xpath(
        '/rpm:repomd/rpm:data[@type="primary"]/rpm:location',
        namespaces=RPMNS,
    )[0].attrib['href']
    primary_xml = fetch_xml('%s/%s' % (repo_url, primary_xml_loc))
    for pkg_element in primary_xml.xpath(
        '/common:metadata/common:package[@type="rpm"]',
        namespaces=RPMNS,
    ):
        name = pkg_element.xpath('common:name', namespaces=RPMNS)[0].text

        if whitelist and name not in whitelist:
            continue

        arch = pkg_element.xpath('common:arch', namespaces=RPMNS)[0].text
        if arch not in rpmUtils.arch.getArchList():
            continue

        yield {
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
        }


def discard_older_rpms(rpms):
    rpms_by_name = {}
    for rpm in rpms:
        name = rpm['name']

        if rpm['location'].endswith('.src.rpm'):
            name = 'src-%s' % name

        if (
                (
                    name not in rpms_by_name
                )
                or
                (
                    rpmUtils.miscutils.compareEVR(
                        rpms_by_name[name]['version'],
                        rpm['version']
                    ) < 0
                )
        ):
            rpms_by_name[name] = rpm

    return rpms_by_name.values()


def verify_repo(repo_url, path, whitelist=None):
    downloaded_rpms = []
    for root, dirs, files in os.walk(path):
        downloaded_rpms.extend([f for f in files if f.endswith('.rpm')])

    for rpm in discard_older_rpms(get_packages(repo_url, whitelist)):
        rpm_filename = os.path.basename(rpm['location'])

        if whitelist and rpm['name'] not in whitelist:
            continue

        if rpm_filename.endswith('.src.rpm'):
            continue

        if rpm_filename not in downloaded_rpms:
            raise RuntimeError(
                'RPM %s is missing from %s' % (
                    rpm['name'],
                    repo_url,
                )
            )


def verify_reposync(config_path, sync_dir, repo_whitelist=None):
    config = ConfigParser.SafeConfigParser()
    with open(config_path) as f:
        config.readfp(f)

    jobs = []
    for repo in config.sections():
        if repo == 'main':
            continue

        if repo_whitelist and repo not in repo_whitelist:
            continue

        if not config.getint(repo, 'enabled'):
            continue

        if config.has_option(repo, 'includepkgs'):
            whitelist = config.get(repo, 'includepkgs').split(' ')
        else:
            whitelist = None

        repo_path = os.path.join(sync_dir, repo)

        jobs.append(
            functools.partial(
                verify_repo,
                config.get(repo, 'baseurl'),
                repo_path,
                whitelist
            )
        )
    vt = testenv.utils.VectorThread(jobs)
    vt.start_all()
    vt.join_all()
