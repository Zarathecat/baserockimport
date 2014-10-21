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


class Package(object):
    '''A package in the processing queue.

    In order to provide helpful errors, this item keeps track of what
    packages depend on it, and hence of why it was added to the queue.

    '''
    def __init__(self, kind, name, version):
        self.kind = kind
        self.name = name
        self.version = version
        self.required_by = []
        self.morphology = None
        self.dependencies = None
        self.is_build_dep = False
        self.version_in_use = version

    def __cmp__(self, other):
        return cmp(self.name, other.name)

    def __repr__(self):
        return '<Package %s-%s>' % (self.name, self.version)

    def __str__(self):
        if len(self.required_by) > 0:
            required_msg = ', '.join(self.required_by)
            required_msg = ', required by: ' + required_msg
        else:
            required_msg = ''
        return '%s-%s%s' % (self.name, self.version, required_msg)

    def add_required_by(self, item):
        self.required_by.append('%s-%s' % (item.name, item.version))

    def match(self, name, version):
        return (self.name==name and self.version==version)

    # FIXME: these accessors are useless, but I want there to be some way
    # of making it clear that some of the state of the Package object is
    # mutable and some of the state is not ...

    def set_morphology(self, morphology):
        self.morphology = morphology

    def set_dependencies(self, dependencies):
        self.dependencies = dependencies

    def set_is_build_dep(self, is_build_dep):
        self.is_build_dep = is_build_dep

    def set_version_in_use(self, version_in_use):
        self.version_in_use = version_in_use
