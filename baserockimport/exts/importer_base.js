// Copyright (C) 2014  Codethink Limited
//
// This program is free software; you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation; version 2 of the License.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License along
// with this program; if not, write to the Free Software Foundation, Inc.,
// 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

// Helper functions for Node.js / npm importer.

exports.getFirstItem = function(info) {
  if (Object.keys(info).length != 1)
    throw(
      util.format("Expected info object containing one item, got %j", info))
  return info[Object.keys(info)[0]];
}
