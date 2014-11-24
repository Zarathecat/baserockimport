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


'''Setup.py for Baserock Import tool.'''


from distutils.core import setup
from distutils.command.build import build

import os
import os.path
import stat
import subprocess


class GenerateResources(build):

    def run(self):
        if not self.dry_run:
            self.generate_manpages()
        build.run(self)

        # Set exec permissions on import extensions.
        for dirname, subdirs, basenames in os.walk('baserockimport/exts'):
            for basename in basenames:
                orig = os.path.join(dirname, basename)
                built = os.path.join('build/lib', dirname, basename)
                st = os.lstat(orig)
                bits = (st.st_mode &
                        (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
                if bits != 0:
                    st2 = os.lstat(built)
                    os.chmod(built, st2.st_mode | bits)

    def generate_manpages(self):
        self.announce('building manpage')
        for x in ['baserock-import']:
            with open('%s.1' % x, 'w') as f:
                subprocess.check_call(['python', x,
                                       '--generate-manpage=%s.1.in' % x,
                                       '--output=%s.1' % x], stdout=f)


setup(name='baserockimport',
      classifiers=[
          'Development Status :: 2 - Pre-Alpha',
          'Environment:: Console',
          'Intended Audience :: Developers',
          'License :: OSI Approved :: GNU General Public License (GPL)',
          'Operating System :: POSIX :: Linux',
          'Programming Language :: Python',
          'Topic :: Software Development :: Build Tools',
          'Topic :: Software Development :: Embedded Systems',
          'Topic :: System :: Archiving :: Packaging',
          'Topic :: System :: Software Distribution',
      ],
      author='Codethink Limited',
      author_email='baserock-dev@baserock.org',
      url='http://www.baserock.org',
      scripts=['baserock-import'],
      packages=['baserockimport'],
      package_data={
          'baserockimport': [
              'data/*',
              'exts/*',
          ]
      },
      cmdclass={
        'build': GenerateResources,
      }
)
