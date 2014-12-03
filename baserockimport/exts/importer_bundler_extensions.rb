#!/usr/bin/env ruby
#
# Extensions to Bundler library which allow using it in importers.
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

require 'bundler'

class << Bundler
  def default_gemfile
    # This is a hack to make things not crash when there's no Gemfile
    Pathname.new('.')
  end
end

module Importer
  module BundlerExtensions
    def locate_gemspec(gem_name, path)
      target = "#{gem_name}.gemspec"
      matches = Dir["#{path}/#{Bundler::Source::Path::DEFAULT_GLOB}"].select do |filename|
        File.basename(filename) == target
      end
      if matches.empty?
        error "Did not find any files matching #{target} within #{path}."
        exit 1
      elsif matches.length > 1
        error "Multiple files matching #{target} found within #{path}. It's " \
              "not clear which one to use!"
        exit 1
      end
      matches[0]
    end

    def create_bundler_definition_for_gemspec(gem_name, gemspec_file)
      # Using the real Gemfile doesn't get great results, because people can put
      # lots of stuff in there that is handy for developers to have but
      # irrelevant if you just want to produce a .gem. Also, there is only one
      # Gemfile per repo, but a repo may include multiple .gemspecs that we want
      # to process individually. Also, some projects don't use Bundler and may
      # not have a Gemfile at all.
      #
      # Instead of reading the real Gemfile, invent one that simply includes the
      # chosen .gemspec. If present, the Gemfile.lock will be honoured.
      fake_gemfile = Bundler::Dsl.new
      fake_gemfile.source('https://rubygems.org')
      fake_gemfile.gemspec({:name => gem_name,
                            :path => File.dirname(gemspec_file)})
      fake_gemfile.to_definition('Gemfile.lock', true)
    end

    def get_spec_for_gem(specs, gem_name)
      found = specs[gem_name].select {|s| Gem::Platform.match(s.platform)}
      if found.empty?
        raise "No Gemspecs found matching '#{gem_name}'"
      elsif found.length != 1
        raise "Unsure which Gem to use for #{gem_name}, got #{found}"
      end
      found[0]
    end

    def directory_is_within(path, expected_subpath)
      File.realpath(expected_subpath).start_with?(File.realpath(path))
    end

    def spec_is_from_current_source_tree(spec, source_dir)
      spec.source.instance_of? Bundler::Source::Path and
        directory_is_within(source_dir, spec.source.path)
    end

    def validate_spec(spec, source_dir_name, expected_version)
      if not spec_is_from_current_source_tree(spec, source_dir_name)
        error "Specified gem '#{spec.name}' doesn't live in the source in " \
              "'#{source_dir_name}'"
        log.debug "SPEC: #{spec.inspect} #{spec.source}"
        exit 1
      end

      if expected_version != nil && spec.version != expected_version
        # This check is brought to you by Coderay, which changes its version
        # number based on an environment variable. Other Gems may do this too.
        error "Source in #{source_dir_name} produces #{spec.full_name}, but " \
              "the expected version was #{expected_version}."
        exit 1
      end
    end
  end
end
