# -*- coding: utf-8 -*-
# Copyright © 2014, 2015  Codethink Limited
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

from __future__ import print_function

import sys
import logging

from importer_base import ImportExtension

PYPI_URL = 'http://pypi.python.org/pypi'

def warn(*args, **kwargs):
    print('%s:' % sys.argv[0], *args, file=sys.stderr, **kwargs)

def error(*args, **kwargs):
    warn(*args, **kwargs)
    sys.exit(1)

def specs_satisfied(version, specs):
    def mapping_error(op):
        # We parse ops with requirements-parser, so any invalid user input
        # should be detected there. This really guards against
        # the pip developers adding some new operation to a requirement.
        error("Invalid op in spec: %s" % op)

    opmap = {'==' : lambda x, y: x == y, '!=' : lambda x, y: x != y,
             '<=' : lambda x, y: x <= y, '>=' : lambda x, y: x >= y,
             '<': lambda x, y: x < y, '>' : lambda x, y: x > y}

    def get_op_func(op):
        return opmap[op] if op in opmap else lambda x, y: mapping_error(op)

    return all([get_op_func(op)(version, sv) for (op, sv) in specs])

def name_or_closest(client, package_name):
    '''Packages on pypi are case insensitive,
    this function returns the package_name it was given if the package
    is found to match exactly, otherwise it returns a version of the name
    that case-insensitively matches the input package_name.

    If no case insensitive match can be found then we return None'''

    # According to http://legacy.python.org/dev/peps/pep-0426/#name
    # "All comparisons of distribution names MUST be case insensitive,
    #  and MUST consider hyphens and underscores to be equivalent."
    #
    # so look for both the hyphenated version that is passed to this function
    # and the underscored version.
    underscored_package_name = package_name.replace('-', '_')

    for name in [package_name, underscored_package_name]:
        results = client.package_releases(name)

        if len(results) > 0:
            logging.debug('Found package %s' % name)
            return name

    logging.debug("Couldn't find exact match for %s,"
                    "searching for a similar match" % package_name)

    results = client.search({'name': [package_name, underscored_package_name]})

    logging.debug("Got the following similarly named packages '%s': %s"
                  % (package_name, str([(result['name'], result['version'])
                            for result in results])))

    logging.debug('Filtering for exact case-insensitive matches')

    results = [result for result in results
                if result['name'].lower() in
                [package_name.lower(), underscored_package_name.lower()]]

    logging.debug('Filtered results: %s' % results)

    return results[0]['name'] if len(results) > 0 else None

# We subclass the ImportExtension to setup the logger,
# so that we can send logs to the import tool's log
class PythonExtension(ImportExtension):
    def __init__(self):
        super(PythonExtension, self).__init__()

    def process_args(self, _):
        import __main__
        __main__.main()
