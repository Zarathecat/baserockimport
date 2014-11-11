# Copyright (C) 2014  Codethink Limited
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.


import morphlib

import copy
import logging
import os


class MorphologySetOnDisk(morphlib.morphset.MorphologySet):
    '''Extensions to the morphlib.MorphologySet class.

    The base class deals only with reading morphologies into memory. This class
    extends it to support reading and writing them from disk.

    FIXME: this should perhaps be merged into the base class in morphlib.

    '''

    def __init__(self, path):
        super(MorphologySetOnDisk, self).__init__()

        self.path = path
        self.loader = morphlib.morphloader.MorphologyLoader()

        if os.path.exists(path):
            self.load_all_morphologies()
        else:
            os.makedirs(path)
            morphlib.gitdir.init(path)

    def load_all_morphologies(self):
        logging.info('Loading all .morph files under %s', self.path)

        gitdir = morphlib.gitdir.GitDirectory(self.path)
        finder = morphlib.morphologyfinder.MorphologyFinder(gitdir)
        for filename in (f for f in finder.list_morphologies()
                         if not gitdir.is_symlink(f)):
            text = finder.read_morphology(filename)
            morph = self.loader.load_from_string(text, filename=filename)
            morph.repo_url = None  # self.root_repository_url
            morph.ref = None  # self.system_branch_name
            self.add_morphology(morph)

    def get_morphology(self, repo_url, ref, filename):
        return self._get_morphology(repo_url, ref, filename)

    def save_morphology(self, filename, morphology):
        self.add_morphology(morphology)
        morphology_to_save = copy.copy(morphology)
        self.loader.unset_defaults(morphology_to_save)
        filename = os.path.join(self.path, filename)
        self.loader.save_to_file(filename, morphology_to_save)
