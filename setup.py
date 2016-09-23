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


if __name__ == '__main__':
    if 'LAGO_VERSION' in os.environ and os.environ['LAGO_VERSION']:
        os.environ['PBR_VERSION'] = os.environ['LAGO_VERSION']
    setup(setup_requires=['pbr'], pbr=True, )
