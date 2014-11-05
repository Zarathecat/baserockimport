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
      scripts=['baserock-import.py'],
      packages=['baserockimport'],
      package_data={
          'baserockimport': [
              'exts/*',
          ]
      },
)
