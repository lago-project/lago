#!/usr/bin/env python
import argparse
import copy
import datetime
import os
import re
import sys
from collections import defaultdict

import dulwich.repo


BUG_URL_REG = re.compile(
    r'.*Bug-Url: https?://bugzilla.*/[^\d]*(?P<bugid>\d+)'
)
VALID_TAG = re.compile(r'^\d+\.\d+$')
FEAT_HEADER = re.compile(r'\nsem-ver:\s*feature\n', flags=re.IGNORECASE)
MAJOR_HEADER = re.compile(r'\nsem-ver:\s*.*break.*\n', flags=re.IGNORECASE)


def fit_to_cols(what, indent, cols=79):
    lines = []
    free_cols = cols - len(indent)
    while len(what) > free_cols:
        if what[free_cols] != ' ':
            try:
                prev_space = what[:free_cols].rindex(' ')
                lines.append(indent + what[:prev_space])
            except ValueError:
                lines.append(indent + what[:free_cols] + '-')
        else:
            lines.append(indent + what[:free_cols])
        what = what[free_cols:]
    lines.append(indent + what)
    return '\n'.join(lines)


def get_bzs_from_commit_msg(commit_msg):
    bugs = []
    for line in commit_msg.split('\n'):
        match = BUG_URL_REG.match(line)
        if match:
            bugs.append('BZ#' + match.groupdict()['bugid'])
    return ' '.join(bugs)


def pretty_commit(commit, version=''):
    subject = commit.message.split('\n', 1)[0]  # noqa
    short_hash = commit.sha().hexdigest()[:8]  # noqa
    author_date = datetime.datetime.fromtimestamp(  # noqa
        int(commit.commit_time)
    ).strftime('%a %b %d %Y')
    author = commit.author  # noqa
    if version:
        version = ' - ' + version
    bugs = get_bzs_from_commit_msg(commit.message)
    changelog_message = fit_to_cols(  # noqa
        '{short_hash}: {subject}'.format(**vars()),
        indent='    ',
    )
    if bugs:
        changelog_bugs = fit_to_cols(
            'FIXED BUGS: {bugs}'.format(**vars()),
            indent='    ',
        ) + '\n'
    else:
        changelog_bugs = ''  # noqa
    return (
        '* {author_date} {author}{version}\n'
        '{changelog_message}\n'
        '{changelog_bugs}'
    ).format(**vars())


def get_tags(repo):
    return {
        commit: os.path.basename(tag_ref)
        for tag_ref, commit
        in repo.get_refs().items()
        if tag_ref.startswith('refs/tags/')
        and VALID_TAG.match(tag_ref[len('refs/tags/'):])
    }


def get_refs(repo):
    refs = defaultdict(set)
    for ref, commit in repo.get_refs().items():
        refs[commit].add(commit)
        refs[commit].add(ref)
    return refs


def fuzzy_matches_ref(fuzzy_ref, ref):
    cur_section = ''
    for path_section in reversed(ref.split('/')):
        cur_section = os.path.normpath(
            os.path.join(path_section, cur_section)
        )
        if fuzzy_ref == cur_section:
            return True
    return False


def fuzzy_matches_refs(fuzzy_ref, refs):
    return any(
        fuzzy_matches_ref(fuzzy_ref, ref)
        for ref in refs
    )


def get_changelog(repo_path, from_commit=None):
    """
    Given a repo path and an option commit/tag/refspec to start from, will
    get the rpm compatible changelog

    Args:
        repo_path (str): path to the git repo
        from_commit (str): refspec (partial commit hash, tag, branch, full
            refspec, partial refspec) to start the changelog from

    Returns:
        str: Rpm compatible changelog
    """
    repo = dulwich.repo.Repo(repo_path)
    tags = get_tags(repo)
    refs = get_refs(repo)
    changelog = []
    maj_version = 0
    feat_version = 0
    fix_version = 0
    start_including = False
    if from_commit is None:
        start_including = True

    for entry in repo.get_walker(reverse=True):
        commit = entry.commit
        commit_sha = commit.sha().hexdigest()
        if commit_sha in tags:
            maj_version, feat_version = tags[commit_sha].split('.')
            maj_version = int(maj_version)
            feat_version = int(feat_version)
            fix_version = 0
        elif MAJOR_HEADER.search(commit.message):
            maj_version += 1
            feat_version = 0
            fix_version = 0
        elif FEAT_HEADER.search(commit.message):
            feat_version += 1
            fix_version = 0
        else:
            fix_version += 1

        version = '%s.%s.%s' % (maj_version, feat_version, fix_version)

        if (
            not start_including
            and not commit_sha.startswith(from_commit)
            and not fuzzy_matches_refs(from_commit, refs.get(commit_sha, []))
        ):
            continue

        start_including = True
        changelog.append(pretty_commit(commit, version))
    return '\n'.join(reversed(changelog))


def get_version(repo_path):
    """
    Given a repo will return the version string, according to semantic
    versioning, counting as non-backwards compatible commit any one with a
    message header that matches (case insensitive)::

        sem-ver: .*break.*

    And as features any commit with a header matching::

        sem-ver: feature

    And counting any other as a bugfix
    """
    repo = dulwich.repo.Repo(repo_path)
    tags = get_tags(repo)
    maj_version = 0
    feat_version = 0
    fix_version = 0

    for entry in repo.get_walker(reverse=True):
        commit = entry.commit
        commit_sha = commit.sha().hexdigest()
        if commit_sha in tags:
            maj_version, feat_version = tags[commit_sha].split('.')
            maj_version = int(maj_version)
            feat_version = int(feat_version)
            fix_version = 0
        elif MAJOR_HEADER.search(commit.message):
            maj_version += 1
            feat_version = 0
            fix_version = 0
        elif FEAT_HEADER.search(commit.message):
            feat_version += 1
            fix_version = 0
        else:
            fix_version += 1

    return '%s.%s.%s' % (maj_version, feat_version, fix_version)


def main(args):

    parser = argparse.ArgumentParser()
    parser.add_argument(
        'repo_path',
        help='Git repo to generate the changelog for'
    )
    subparsers = parser.add_subparsers()
    changelog_parser = subparsers.add_parser('changelog')
    changelog_parser.add_argument(
        '--from-commit', default=None,
        help='Commit to start the changelog from'
    )
    changelog_parser.set_defaults(func=get_changelog)
    version_parser = subparsers.add_parser('version')
    version_parser.set_defaults(func=get_version)
    args = parser.parse_args(args)

    params = copy.deepcopy(vars(args))
    params.pop('func')
    return args.func(**params)


if __name__ == '__main__':

    print main(sys.argv[1:])
