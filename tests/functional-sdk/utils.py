from __future__ import absolute_import

import os
import uuid
import random


class RandomizedDir(object):
    def __init__(self, path, depth, max_files=30):
        """
        Create a random number of directories with a random number of files,
        with random one line data in each file


        Args:
            path(str): root path to create the directory
            depth(int): In each round a random number between 1 and ``depth``
                directories will be created. For each directory in the next
                round depth will be decreased by one.
                Must be greater than 1.
            max_files(int): In each directory a random number between 0
                to ``max_files`` files will be created in each directory.

        Returns:
            None
        """
        if depth <= 1:
            raise ValueError('depth must be greater than 1')

        self.path = path
        self.depth = depth
        self.max_files = max_files
        self.files = []
        self.dirs = []
        self._used_uuids = set()
        self._randomized_dir(self.path, self.depth)

    def _randomized_dir(self, path, depth):
        if depth <= 1:
            return
        local_depth = random.randint(1, depth)
        for level in range(local_depth):
            num_files = random.randint(0, self.max_files)
            for rand_file in range(num_files):
                fname = os.path.join(path, self._uuid().hex[-8:])
                with open(fname, 'w') as f:
                    f.write(self._uuid().hex)
                self.files.append(fname)
            rand_dir = os.path.join(path, self._uuid().hex[-8:])
            os.makedirs(rand_dir)
            self.dirs.append(rand_dir)
            self._randomized_dir(rand_dir, local_depth - 1)

    def _uuid(self):
        candidate = None
        while True:
            candidate = uuid.uuid4()
            # the probability is really low to have a collision
            # but who knows..
            if candidate not in self._used_uuids:
                break
        self._used_uuids.add(candidate)
        return candidate
