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
import six

import json
import logging
import os


class LorrySetError(Exception):
    pass


class LorrySet(object):
    '''Manages a set of .lorry files.

    A LorrySet instance operates on all the .lorry files inside the path given
    at construction time. This includes .lorry files in subdirectories of the
    path.

    A lorry *entry* describes the upstream repository for a given project,
    which is associated to a name such as 'ruby-gems/chef' or 'gcc-tarball'. A
    lorry *file* contains one or more *entries*. The filename of a lorry file
    is not necessarily linked to the name of any lorry entry that it contains.

    '''

    def __init__(self, lorries_path):
        '''Initialise a LorrySet instance for the given directory.

        This will load and parse all of the .lorry files inside 'lorries_path'
        into memory.

        '''
        self.path = lorries_path

        if os.path.exists(lorries_path):
            self.data = self._parse_all_lorries()
        else:
            os.makedirs(lorries_path)
            self.data = {}

    def all_lorry_files(self):
        '''Return the path of each lorry file in this set.'''
        for dirpath, dirnames, filenames in os.walk(self.path):
            for filename in filenames:
                if filename.endswith('.lorry'):
                    yield os.path.join(dirpath, filename)

    def _parse_all_lorries(self):
        lorry_set = {}
        for lorry_file in self.all_lorry_files():
            lorry = self._parse_lorry(lorry_file)

            lorry_items = lorry.items()

            for key, value in lorry_items:
                if key in lorry_set:
                    raise LorrySetError(
                        '%s: duplicates existing lorry %s' % (lorry_file, key))

            lorry_set.update(lorry_items)

        return lorry_set

    def _parse_lorry(self, lorry_file):
        try:
            with open(lorry_file, 'r') as f:
                lorry = json.load(f)
            return lorry
        except ValueError as e:
            raise LorrySetError(
                "Error parsing %s: %s" % (lorry_file, e))

    def get_lorry(self, name):
        '''Return the lorry entry for the named project.'''
        return {name: self.data[name]}

    def find_lorry_for_package(self, kind, package_name):
        '''Find the lorry entry for a given foreign package, or return None.

        This makes use of an extension to the .lorry format made by the
        Baserock Import tool. Fields follow the form 'x-products-$KIND'
        and specify the name of a package in the foreign packaging universe
        named $KIND.

        '''
        key = 'x-products-%s' % kind
        for name, lorry in self.data.iteritems():
            products = lorry.get(key, [])
            for entry in products:
                if entry == package_name:
                    return {name: lorry}

        return None

    def _check_for_conflicts_in_standard_fields(self, existing, new):
        '''Ensure that two lorries for the same project do actually match.'''
        for field, value in existing.iteritems():
            if field.startswith('x-'):
                continue
            if field == 'url':
                # FIXME: need a much better way of detecting whether the URLs
                # are equivalent ... right now HTTP vs. HTTPS will cause an
                # error, for example!
                matches = (value.rstrip('/') == new[field].rstrip('/'))
            else:
                matches = (value == new[field])
            if not matches:
                raise LorrySetError(
                    'Lorry %s conflicts with existing entry %s at field %s' %
                    (new, existing, field))

    def _merge_products_fields(self, existing, new):
        '''Merge the x-products- fields from new lorry into an existing one.'''
        is_product_field = lambda x: x.startswith('x-products-')

        existing_fields = [f for f in existing.iterkeys() if
                           is_product_field(f)]
        new_fields = [f for f in new.iterkeys() if f not in existing_fields and
                      is_product_field(f)]

        for field in existing_fields:
            existing[field].extend(new[field])
            existing[field] = list(set(existing[field]))

        for field in new_fields:
            existing[field] = new[field]

    def _add_lorry_entry_to_lorry_file(self, filename, entry):
        if os.path.exists(filename):
            with open(filename) as f:
                contents = json.load(f)
        else:
            contents = {}

        contents.update(entry)

        with morphlib.savefile.SaveFile(filename, 'w') as f:
            json.dump(contents, f, indent=4, separators=(',', ': '),
                      sort_keys=True)

    def add(self, filename, lorry_entry):
        '''Add a lorry entry to the named .lorry file.

        The lorry_entry should follow the on-disk format for a lorry stanza,
        which is a dict of one entry mapping the name of the entry to its
        contents.

        The .lorry file will be created if it doesn't exist.

        '''
        logging.debug('Adding %s to lorryset', filename)

        filename = os.path.join(self.path, '%s.lorry' % filename)

        assert len(lorry_entry) == 1

        project_name = lorry_entry.keys()[0]
        info = lorry_entry.values()[0]

        if len(project_name) == 0:
            raise LorrySetError(
                'Invalid lorry %s: %s' % (filename, lorry_entry))

        if not isinstance(info.get('url'), six.string_types):
            raise LorrySetError(
                'Invalid URL in lorry %s: %s' % (filename, info.get('url')))

        if project_name in self.data:
            stored_lorry = self.get_lorry(project_name)

            self._check_for_conflicts_in_standard_fields(
                stored_lorry[project_name], lorry_entry[project_name])
            self._merge_products_fields(
                stored_lorry[project_name], lorry_entry[project_name])
            lorry_entry = stored_lorry
        else:
            self.data[project_name] = info

        self._add_lorry_entry_to_lorry_file(filename, lorry_entry)
