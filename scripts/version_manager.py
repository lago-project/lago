#!/usr/bin/env python2

from __future__ import print_function

import argparse
import copy
import datetime
import logging
import os
import re
import sys
from collections import defaultdict, OrderedDict

import dulwich.repo
import dulwich.walk

LOGGER = logging.getLogger(__name__)

BUG_URL_REG = re.compile(
    r'.*Bug-Url: https?://bugzilla.*/[^\d]*(?P<bugid>\d+)'
)
VALID_TAG = re.compile(r'^\d+\.\d+$')
FEAT_HEADER = re.compile(r'\nsem-ver:\s*feature\n', flags=re.IGNORECASE)
MAJOR_HEADER = re.compile(r'\nsem-ver:\s*.*break.*\n', flags=re.IGNORECASE)


def fit_to_cols(what, indent, cols=79):
    lines = []
    free_cols = cols - len(indent)
    while len(what) > free_cols and ' ' in what.lstrip():
        cutpoint = free_cols
        extra_indent = ''
        if what[free_cols] != ' ':
            try:
                prev_space = what[:free_cols].rindex(' ')
                lines.append(indent + what[:prev_space])
                cutpoint = prev_space + 1
                extra_indent = '          '
            except ValueError:
                lines.append(indent + what[:free_cols] + '-')
        else:
            lines.append(indent + what[:free_cols])
        what = extra_indent + what[cutpoint:]
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
        ('* {author_date} {author}{version}\n'
         if version is not None else '') + '{changelog_message}\n' +
        '{changelog_bugs}'
    ).format(**vars())


def get_tags(repo):
    return {
        commit: os.path.basename(tag_ref)
        for tag_ref, commit in repo.get_refs().items()
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
        cur_section = os.path.normpath(os.path.join(path_section, cur_section))
        if fuzzy_ref == cur_section:
            return True
    return False


def fuzzy_matches_refs(fuzzy_ref, refs):
    return any(fuzzy_matches_ref(fuzzy_ref, ref) for ref in refs)


def get_children_per_parent(repo_path):
    repo = dulwich.repo.Repo(repo_path)
    children_per_parent = defaultdict(set)

    for entry in repo.get_walker(order=dulwich.walk.ORDER_TOPO):
        for parent in entry.commit.parents:
            children_per_parent[parent].add(entry.commit.sha().hexdigest())

    return children_per_parent


def get_first_parents(repo_path):
    repo = dulwich.repo.Repo(repo_path)
    #: these are the commits that are parents of more than one other commit
    first_parents = []
    on_merge = False

    for entry in repo.get_walker(order=dulwich.walk.ORDER_TOPO):
        commit = entry.commit
        if not commit.parents:
            if commit.sha().hexdigest() not in first_parents:
                first_parents.append(commit.sha().hexdigest())
        elif len(commit.parents) == 1 and not on_merge:
            if commit.sha().hexdigest() not in first_parents:
                first_parents.append(commit.sha().hexdigest())
            if commit.parents[0] not in first_parents:
                first_parents.append(commit.parents[0])
        elif len(commit.parents) > 1 and not on_merge:
            on_merge = True
            if commit.sha().hexdigest() not in first_parents:
                first_parents.append(commit.sha().hexdigest())
            if commit.parents[0] not in first_parents:
                first_parents.append(commit.parents[0])
        elif commit.parents and commit.sha().hexdigest() in first_parents:
            if commit.parents[0] not in first_parents:
                first_parents.append(commit.parents[0])

    if commit.parents:
        # If this is the case, we have a shallow git clone
        # which means that we don't have the metadata of the
        # first's commit parent.
        LOGGER.debug(
            'This is a shallow git clone,'
            ' removing the first\'s commit parent.'
        )
        first_parents.pop()

    return first_parents


def has_firstparent_child(sha, first_parents, parents_per_child):
    return any(
        child for child in parents_per_child[sha] if child in first_parents
    )


def get_merged_commits(repo, commit, first_parents, children_per_parent):
    merge_children = set()

    to_explore = set([commit.sha().hexdigest()])

    while to_explore:
        next_sha = to_explore.pop()
        next_commit = repo.get_object(next_sha)
        if (
            next_sha not in first_parents and not has_firstparent_child(
                next_sha, first_parents, children_per_parent
            ) or next_sha in commit.parents
        ):
            merge_children.add(next_sha)

        non_first_parents = (
            parent for parent in next_commit.parents
            if parent not in first_parents
        )
        for child_sha in non_first_parents:
            if child_sha not in merge_children and child_sha != next_sha:
                to_explore.add(child_sha)

    return merge_children


def get_children_per_first_parent(repo_path):
    repo = dulwich.repo.Repo(repo_path)
    first_parents = get_first_parents(repo_path)
    children_per_parent = get_children_per_parent(repo_path)
    children_per_first_parent = OrderedDict()

    for first_parent in first_parents:
        commit = repo.get_object(first_parent)
        if len(commit.parents) > 1:
            children = get_merged_commits(
                repo=repo,
                commit=commit,
                first_parents=first_parents,
                children_per_parent=children_per_parent,
            )
        else:
            children = set()
        children_per_first_parent[first_parent] = children

    return children_per_first_parent


def get_version(commit, tags, maj_version=0, feat_version=0, fix_version=0):
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

    version = (maj_version, feat_version, fix_version)
    return version


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

    cur_line = ''
    if from_commit is None:
        start_including = True

    for commit_sha, children in reversed(
        get_children_per_first_parent(repo_path).items()
    ):
        commit = repo.get_object(commit_sha)
        maj_version, feat_version, fix_version = get_version(
            commit=commit,
            tags=tags,
            maj_version=maj_version,
            feat_version=feat_version,
            fix_version=fix_version,
        )
        version = '%s.%s.%s' % (maj_version, feat_version, fix_version)

        if (
            start_including or commit_sha.startswith(from_commit)
            or fuzzy_matches_refs(from_commit, refs.get(commit_sha, []))
        ):
            cur_line = pretty_commit(
                commit,
                version,
            )
            for child in children:
                cur_line += pretty_commit(repo.get_object(child), version=None)
            start_including = True
            changelog.append(cur_line)

    return '\n'.join(reversed(changelog))


def get_current_version(repo_path):
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

    for commit_sha in reversed(get_first_parents(repo_path)):
        commit = repo.get_object(commit_sha)
        maj_version, feat_version, fix_version = get_version(
            commit=commit,
            tags=tags,
            maj_version=maj_version,
            feat_version=feat_version,
            fix_version=fix_version,
        )

    return '%s.%s.%s' % (maj_version, feat_version, fix_version)


def set_logging():
    logging.basicConfig(level=logging.DEBUG)


def main(args):
    set_logging()

    parser = argparse.ArgumentParser()
    parser.add_argument(
        'repo_path', help='Git repo to generate the changelog for'
    )
    subparsers = parser.add_subparsers()
    changelog_parser = subparsers.add_parser('changelog')
    changelog_parser.add_argument(
        '--from-commit',
        default=None,
        help='Commit to start the changelog from'
    )
    changelog_parser.set_defaults(func=get_changelog)
    version_parser = subparsers.add_parser('version')
    version_parser.set_defaults(func=get_current_version)
    args = parser.parse_args(args)

    params = copy.deepcopy(vars(args))
    params.pop('func')
    return args.func(**params)


if __name__ == '__main__':

    print(main(sys.argv[1:]))
