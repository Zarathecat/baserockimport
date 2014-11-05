# Extensions for the Omnibus tool that allow using it to generate morphologies.
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

require 'omnibus'

require 'optparse'
require 'rubygems/commands/build_command'
require 'rubygems/commands/install_command'
require 'shellwords'

class Omnibus::Builder
  # It's possible to use `gem install` in build commands, which is a great
  # way of subverting the dependency tracking Omnibus provides. It's done
  # in `omnibus-chef/config/software/chefdk.rb`, for example.
  #
  # To handle this, here we extend the class that executes the build commands
  # to detect when `gem install` is run. It uses the Gem library to turn the
  # commandline back into a Bundler::Dependency object that we can use.
  #
  # We also trap `gem build` so we know when a software component is a RubyGem
  # that should be handled by 'rubygems.to_chunk'.

  class GemBuildCommandParser < Gem::Commands::BuildCommand
    def gemspec_path(args)
      handle_options args
      if options[:args].length != 1
        raise "Invalid `gem build` commandline: 1 argument expected, got " \
               "#{options[:args]}."
      end
      options[:args][0]
    end
  end

  class GemInstallCommandParser < Gem::Commands::InstallCommand
    def dependency_list_from_commandline(args)
      handle_options args

      # `gem install foo*` is sometimes used when installing a locally built
      # Gem, to avoid needing to know the exact version number that was built.
      # We only care about remote Gems being installed, so anything with a '*'
      # in its name can be ignored.
      gem_names = options[:args].delete_if { |name| name.include?('*') }

      gem_names.collect do |gem_name|
        Bundler::Dependency.new(gem_name, options[:version])
      end
    end
  end

  def gem(command, options = {})
    # This function re-implements the 'gem' function in the build-commands DSL.
    if command.start_with? 'build'
      parser = GemBuildCommandParser.new
      args = Shellwords.split(command).drop(1)
      if built_gemspec != nil
        raise "More than one `gem build` command was run as part f the build " \
              "process. The 'rubygems.to_chunk' program currently supports " \
              "only one .gemspec build per chunk, so this can't be " \
              "processed automatically."
      end
      @built_gemspec = parser.gemspec_path(args)
    elsif command.start_with? 'install'
      parser = GemInstallCommandParser.new
      args = Shellwords.split(command).drop(1)
      args_without_build_flags = args.take_while { |item| item != '--' }
      gems = parser.dependency_list_from_commandline(args_without_build_flags)
      manually_installed_rubygems.concat gems
    end
  end

  def built_gemspec
    @built_gemspec
  end

  def manually_installed_rubygems
    @manually_installed_rubygems ||= []
  end
end
