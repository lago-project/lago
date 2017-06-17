import os
import subprocess
from setuptools import setup


def check_output(args):
    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = proc.communicate()

    if proc.returncode:
        raise RuntimeError(
            'Failed to run %s\nrc=%s\nstdout=\n%sstderr=%s' %
            (args, proc.returncode, stdout, stderr)
        )

    return stdout


def get_version(project_dir=os.curdir):
    """
    Retrieves the version of the package, from the PKG-INFO file or generates
    it with the version script
    Returns:
        str: Version for the package
    Raises:
        RuntimeError: If the version could not be retrieved
    """
    if 'LAGO_VERSION' in os.environ and os.environ['LAGO_VERSION']:
        return os.environ['LAGO_VERSION']

    version = None
    pkg_info_file = os.path.join(project_dir, 'PKG-INFO')
    version_manager = os.path.join(project_dir, 'scripts/version_manager.py')
    if os.path.exists(pkg_info_file):
        with open(pkg_info_file) as info_fd:
            for line in info_fd.readlines():
                if line.startswith('Version: '):
                    version = line.split(' ', 1)[-1]

    elif os.path.exists(version_manager):
        version = check_output([version_manager, project_dir,
                                'version']).strip()

    if version is None:
        raise RuntimeError('Failed to get package version')

    # py3 compatibility step
    if not isinstance(version, str) and isinstance(version, bytes):
        version = version.decode()

    return version


if __name__ == '__main__':
    os.environ['PBR_VERSION'] = get_version()
    setup(
        setup_requires=['pbr', 'dulwich'],
        pbr=True,
    )
