#!/usr/bin/env python
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

import unittest
import random

import imp
python_find_deps = imp.load_source('python_find_deps', 'python.find_deps')

from pkg_resources import parse_requirements, parse_version

def reverse(xs):
    return xs[::-1]

class ConflictDetectionTests(unittest.TestCase):

    def setUp(self):
        reqs = ['a == 0.1', 'a == 0.2']
        self.test_requirements = parse_requirements(reqs)

    def run_conflict_test(self, requirements, expected_conflicts):
        names = set([r.project_name for r in requirements])

        with self.assertRaises(python_find_deps.ConflictError) as cm:
            python_find_deps.resolve_specs(requirements)

        for name in names:
            _exps = [(op, parse_version(v)) for (op, v)
                     in expected_conflicts[name]]

            self.assertEqual(cm.exception.specs, _exps)

    def run_conflict_test_reversed(self, requirements, expected_conflicts):
        # First reverse conflicts to get them in the right order
        reversed_expected_conflicts = {k: reverse(v) for (k, v)
                                            in expected_conflicts.iteritems()}

        self.run_conflict_test(reverse(requirements),
                               reversed_expected_conflicts)

    def run_no_conflict_test(self, requirements, expected_specs):
        print python_find_deps.resolve_specs(requirements)

        names = set([r.project_name for r in requirements])

        for name in names:
            _exps = set([(op, parse_version(v)) for (op, v)
                        in expected_specs[name]])

            _specs = python_find_deps.resolve_specs(requirements)[name]

            self.assertEqual(_specs, _exps)

    def test_eqs_eqs(self):
        requirements = list(parse_requirements(['a == 0.1', 'a == 0.2']))
        expected_conflicts = {'a': [('==', '0.1'), ('==', '0.2')]}

        self.run_conflict_test(requirements, expected_conflicts)
        self.run_conflict_test_reversed(requirements, expected_conflicts)

    def test_eqs_nt_eq(self):
        # == x conflicts with != x
        requirements = list(parse_requirements(['a == 0.1', 'a != 0.1']))
        expected_conflicts = {'a': [('==', '0.1'), ('!=', '0.1')]}

        self.run_conflict_test(requirements, expected_conflicts)
        self.run_conflict_test_reversed(requirements, expected_conflicts)

    def test_eqs_lt(self):
        # == x conflicts with < y if x >= y
        requirements = list(parse_requirements(['a == 0.2', 'a < 0.1']))

        expected_conflicts = {'a': [('==', '0.2'), ('<', '0.1')]}

        self.run_conflict_test(requirements, expected_conflicts)
        self.run_conflict_test_reversed(requirements, expected_conflicts)

        requirements = list(parse_requirements(['a == 0.1', 'a < 0.1']))

        expected_conflicts = {'a': [('==', '0.1'), ('<', '0.1')]}

        self.run_conflict_test(requirements, expected_conflicts)
        self.run_conflict_test_reversed(requirements, expected_conflicts)

    def test_eqs_gt(self):
        # == x conflicts with > y if x <= y
        requirements = list(parse_requirements(['a == 0.1', 'a > 0.1']))

        expected_conflicts = {'a': [('==', '0.1'), ('>', '0.1')]}

        self.run_conflict_test(requirements, expected_conflicts)
        self.run_conflict_test_reversed(requirements, expected_conflicts)

        requirements = list(parse_requirements(['a == 0.1', 'a > 0.2']))

        expected_conflicts = {'a': [('==', '0.1'), ('>', '0.2')]}

        self.run_conflict_test(requirements, expected_conflicts)
        self.run_conflict_test_reversed(requirements, expected_conflicts)

    def test_eqs_lte(self):
        # == x conflicts with <= y if x > y
        requirements = list(parse_requirements(['a == 0.2', 'a <= 0.1']))

        expected_conflicts = {'a': [('==', '0.2'), ('<=', '0.1')]}

        self.run_conflict_test(requirements, expected_conflicts)
        self.run_conflict_test_reversed(requirements, expected_conflicts)

        requirements = list(parse_requirements(['a == 0.1', 'a <= 0.1']))  # no conflict
        expected_specs = {'a': set([('==', '0.1'), ('<=', '0.1')])}

        self.run_no_conflict_test(requirements, expected_specs)
        self.run_no_conflict_test(reverse(requirements), expected_specs)

    def test_eq_gte(self):
        # == x conflicts with >= y if x < y
        requirements = list(parse_requirements(['a == 0.1', 'a >= 0.2']))

        expected_conflicts = {'a': [('==', '0.1'), ('>=', '0.2')]}

        self.run_conflict_test(requirements, expected_conflicts)
        self.run_conflict_test_reversed(requirements, expected_conflicts)

        requirements = list(parse_requirements(['a == 0.1', 'a >= 0.1']))
        expected_specs = {'a': set([('==', '0.1'), ('>=', '0.1')])}

        self.run_no_conflict_test(requirements, expected_specs)
        self.run_no_conflict_test(reverse(requirements), expected_specs)

    def test_lt_lt(self):
        # < x < y never conflicts
        requirements = list(parse_requirements(['a < 0.1', 'a < 0.1']))
        expected_specs = {'a': set([('<', '0.1')])}

        self.run_no_conflict_test(requirements, expected_specs)
        self.run_no_conflict_test(reverse(requirements), expected_specs)

        requirements = list(parse_requirements(['a < 0.1', 'a < 0.2']))
        expected_specs = {'a': set([('<', '0.1'), ('<', '0.2')])}

        self.run_no_conflict_test(requirements, expected_specs)
        self.run_no_conflict_test(reverse(requirements), expected_specs)

    def test_lt_gt(self):
        # < x conflicts with > y if x <= y
        requirements = list(parse_requirements(['a < 0.1', 'a > 0.1']))

        expected_conflicts = {'a': [('<', '0.1'), ('>', '0.1')]}

        self.run_conflict_test(requirements, expected_conflicts)
        self.run_conflict_test_reversed(requirements, expected_conflicts)

        requirements = list(parse_requirements(['a < 0.1', 'a > 0.2']))

        expected_conflicts = {'a': [('<', '0.1'), ('>', '0.2')]}

        self.run_conflict_test(requirements, expected_conflicts)
        self.run_conflict_test_reversed(requirements, expected_conflicts)

    def test_lt_lte(self):
        # < x <= y never conflicts
        requirements = list(parse_requirements(['a < 0.1', 'a <= 0.1']))
        expected_specs = {'a': set([('<', '0.1'), ('<=', '0.1')])}

        self.run_no_conflict_test(requirements, expected_specs)
        self.run_no_conflict_test(reverse(requirements), expected_specs)

        requirements = list(parse_requirements(['a < 0.1', 'a <= 0.2']))
        expected_specs = {'a': set([('<', '0.1'), ('<=', '0.2')])}

        self.run_no_conflict_test(requirements, expected_specs)
        self.run_no_conflict_test(reverse(requirements), expected_specs)

    def test_lt_gte(self):
        # < x conflicts with >= y if x <= y
        requirements = list(parse_requirements(['a < 0.1', 'a >= 0.1']))

        expected_conflicts = {'a': [('<', '0.1'), ('>=', '0.1')]}

        self.run_conflict_test(requirements, expected_conflicts)
        self.run_conflict_test_reversed(requirements, expected_conflicts)

        requirements = list(parse_requirements(['a < 0.1', 'a >= 0.2']))

        expected_conflicts = {'a': [('<', '0.1'), ('>=', '0.2')]}

        self.run_conflict_test(requirements, expected_conflicts)
        self.run_conflict_test_reversed(requirements, expected_conflicts)

    def test_gt_gt(self):
        # > x > y never conflicts
        requirements = list(parse_requirements(['a > 0.1', 'a > 0.1']))
        expected_specs = {'a': set([('>', '0.1')])}

        self.run_no_conflict_test(requirements, expected_specs)
        self.run_no_conflict_test(reverse(requirements), expected_specs)

        requirements = list(parse_requirements(['a > 0.1', 'a > 0.2']))
        expected_specs = {'a': set([('>', '0.1'), ('>', '0.2')])}

        self.run_no_conflict_test(requirements, expected_specs)
        self.run_no_conflict_test(reverse(requirements), expected_specs)

    def test_gt_lte(self):
        # > x conflicts with <= y if x >= y
        requirements = list(parse_requirements(['a > 0.1', 'a <= 0.1']))

        expected_conflicts = {'a': [('>', '0.1'), ('<=', '0.1')]}

        self.run_conflict_test(requirements, expected_conflicts)
        self.run_conflict_test_reversed(requirements, expected_conflicts)

        requirements = list(parse_requirements(['a > 0.2', 'a <= 0.1']))

        expected_conflicts = {'a': [('>', '0.2'), ('<=', '0.1')]}

        self.run_conflict_test(requirements, expected_conflicts)
        self.run_conflict_test_reversed(requirements, expected_conflicts)

    def test_gt_gte(self):
         # > x >= y never conflicts
        requirements = list(parse_requirements(['a > 0.1', 'a >= 0.1']))
        expected_specs = {'a': set([('>', '0.1'), ('>=', '0.1')])}

        self.run_no_conflict_test(requirements, expected_specs)
        self.run_no_conflict_test(reverse(requirements), expected_specs)

        requirements = list(parse_requirements(['a > 0.1', 'a >= 0.2']))
        expected_specs = {'a': set([('>', '0.1'), ('>=', '0.2')])}

        self.run_no_conflict_test(requirements, expected_specs)
        self.run_no_conflict_test(reverse(requirements), expected_specs)

    def test_lte_lte(self):
         # <= x <= y never conflicts
        requirements = list(parse_requirements(['a <= 0.1', 'a <= 0.1']))
        expected_specs = {'a': set([('<=', '0.1')])}

        self.run_no_conflict_test(requirements, expected_specs)
        self.run_no_conflict_test(reverse(requirements), expected_specs)

        requirements = list(parse_requirements(['a <= 0.1', 'a <= 0.2']))
        expected_specs = {'a': set([('<=', '0.1'), ('<=', '0.2')])}

        self.run_no_conflict_test(requirements, expected_specs)
        self.run_no_conflict_test(reverse(requirements), expected_specs)

    def test_lte_gte(self):
        # <= x conflicts with >= y if x < y
        # note that if x == y, then the two specs don't add any constraint
        requirements = list(parse_requirements(['a <= 0.1', 'a >= 0.1']))

        expected_specs= {'a': set([('<=', '0.1'), ('>=', '0.1')])}

        self.run_no_conflict_test(requirements, expected_specs)
        self.run_no_conflict_test(reverse(requirements), expected_specs)

        requirements = list(parse_requirements(['a <= 0.1', 'a >= 0.2']))

        expected_conflicts = {'a': [('<=', '0.1'), ('>=', '0.2')]}

        self.run_conflict_test(requirements, expected_conflicts)
        self.run_conflict_test_reversed(requirements, expected_conflicts)

    def test_gte_gte(self):
         # >= x >= y never conflicts
        requirements = list(parse_requirements(['a >= 0.1', 'a >= 0.1']))
        expected_specs = {'a': set([('>=', '0.1')])}

        self.run_no_conflict_test(requirements, expected_specs)
        self.run_no_conflict_test(reverse(requirements), expected_specs)

        requirements = list(parse_requirements(['a >= 0.1', 'a >= 0.2']))
        expected_specs = {'a': set([('>=', '0.1'), ('>=', '0.2')])}

        self.run_no_conflict_test(requirements, expected_specs)
        self.run_no_conflict_test(reverse(requirements), expected_specs)

    def test_ne(self):
        # != can only conflict with == (which is tested above)
        for s in ['<', '>', '<=', '>=']:
            requirements = list(parse_requirements(['a != 0.1', 'a %s 0.1' % s]))
            expected_specs = {'a': set([('!=', '0.1'), ('%s' % s, '0.1')])}

            self.run_no_conflict_test(requirements, expected_specs)
            self.run_no_conflict_test(reverse(requirements), expected_specs)

            requirements = list(parse_requirements(['a != 0.1', 'a %s 0.2' % s]))
            expected_specs = {'a': set([('!=', '0.1'), ('%s' % s, '0.2')])}

            self.run_no_conflict_test(requirements, expected_specs)
            self.run_no_conflict_test(reverse(requirements), expected_specs)

    def test_unmatched(self):
        # Run all permutations, fail if we get an UnmatchedException
        # or something else we weren't expecting
        comparitors = ['==', '!=', '<', '>', '<=', '>=']
        vs = [('0.1', '0.1'), ('0.1', '0.2'),
              ('%s' % random.randint(0, 100), '%s' % random.randint(0, 100))]

        for (vx, vy) in vs:
            for cmpx in comparitors:
                for cmpy in comparitors:
                    requirements = parse_requirements(['a %s %s' % (cmpx, vx),
                                                       'a %s %s' % (cmpy, vy)])
                    try:
                        python_find_deps.resolve_specs(requirements)
                    except python_find_deps.ConflictError:
                        pass
                    except python_find_deps.UnmatchedException as e:
                        self.fail('Got UnmatchedException: %s' % e)
                    except Exception as e:
                        self.fail('Got some other unexpected Exception: %s' % e)

    def test_cause_unmatched(self):
        requirements_specs = list(parse_requirements(['a == 0.1', 'a == 0.1']))

        # replace our parsed specs with invalid specs
        # specifically, specs with invalid operators
        #
        # note, one spec won't do, we're validating the specs logically
        # not syntactically; we assume the specs themselves have been parsed
        # by pkg_resources which will do the validation for us.
        #
        # so we need two specs to force a check for a conflict,
        # an UnmatchedError should occur if neither of the specs
        # contain an operator recognised by the conflict detector
        # e.g. '===', which is undefined in a spec
        requirements_specs[0].specs = [('===', '0.1')]
        requirements_specs[1].specs = [('===', '0.1')]

        with self.assertRaises(python_find_deps.UnmatchedError):
            specs = python_find_deps.resolve_specs(requirements_specs)

    def test_distinct_requirements_no_conflict(self):
        requirements = list(parse_requirements(['a == 0.1', 'b == 0.1']))

        specs = python_find_deps.resolve_specs(requirements)

        expected_specs = {'a': set([('==', parse_version('0.1'))]),
                          'b': set([('==', parse_version('0.1'))])}

        self.assertEqual(specs, expected_specs)


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(ConflictDetectionTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
