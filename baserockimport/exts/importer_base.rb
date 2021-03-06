#!/usr/bin/env ruby
#
# Base class for importers written in Ruby
#
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

require 'json'
require 'logger'
require 'optparse'
require 'yaml'

module Importer
  class Base
    private

    def create_option_parser(banner, description)
      opts = OptionParser.new

      opts.banner = banner

      opts.on('-?', '--help', 'print this help') do
        puts opts
        print "\n", description
        exit 255
      end
    end

    def log
      @logger ||= create_logger
    end

    def error(message)
      log.error(message)
      STDERR.puts(message)
    end

    def local_data_path(file)
      # Return the path to 'file' relative to the currently running program.
      # Used as a simple mechanism of finding local data files.
      script_dir = File.dirname(__FILE__)
      File.join(script_dir, '..', 'data', file)
    end

    def write_lorry(file, lorry)
      format_options = { :indent => '    ' }
      file.puts(JSON.pretty_generate(lorry, format_options))
    end

    def write_morph(file, morph)
      file.write(YAML.dump(morph))
    end

    def write_dependencies(file, dependencies)
      format_options = { :indent => '    ' }
      file.puts(JSON.pretty_generate(dependencies, format_options))
    end

    def create_logger
      # Use the logger that was passed in from the 'main' import process, if
      # detected.
      log_fd = ENV['MORPH_LOG_FD']
      if log_fd
        log_stream = IO.new(Integer(log_fd), 'w')
        logger = Logger.new(log_stream)
        logger.level = Logger::DEBUG
        logger.formatter = proc { |severity, datetime, progname, msg| "#{msg}\n" }
      else
        logger = Logger.new('/dev/null')
      end
      logger
    end
  end
end
