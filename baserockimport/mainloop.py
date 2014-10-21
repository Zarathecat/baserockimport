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


import cliapp
import morphlib
import networkx

import json
import logging
import os
import tempfile
import time

import baserockimport


class GitDirectory(morphlib.gitdir.GitDirectory):
    def __init__(self, dirname):
        super(GitDirectory, self).__init__(dirname)

        # Work around strange/unintentional behaviour in GitDirectory class
        # when 'repopath' isn't a Git repo. If 'repopath' is contained
        # within a Git repo then the GitDirectory will traverse up to the
        # parent repo, which isn't what we want in this case.
        #
        # FIXME: this should be a change to the base class, which should take
        # a flag at construct time saying 'traverse_upwards_to_find_root' or
        # some such.
        if self.dirname != dirname:
            logging.error(
                'Got git directory %s for %s!', self.dirname, dirname)
            raise cliapp.AppException(
                '%s is not the root of a Git repository' % dirname)

    def has_ref(self, ref):
        try:
            self._rev_parse(ref)
            return True
        except morphlib.gitdir.InvalidRefError:
            return False


class BaserockImportException(cliapp.AppException):
    pass


def find(iterable, match):
    return next((x for x in iterable if match(x)), None)


def run_extension(filename, args, cwd='.'):
    output = []
    errors = []

    ext_logger = logging.getLogger(filename)

    def report_extension_stdout(line):
        output.append(line)

    def report_extension_stderr(line):
        errors.append(line)

    def report_extension_logger(line):
        ext_logger.debug(line)

    ext = morphlib.extensions.ExtensionSubprocess(
        report_stdout=report_extension_stdout,
        report_stderr=report_extension_stderr,
        report_logger=report_extension_logger,
    )

    def extensions_dir():
        module_dir = os.path.dirname(baserockimport.__file__)
        return os.path.join(module_dir, '..', 'exts')

    extension_path = os.path.join(extensions_dir(), filename)

    logging.debug("Running %s %s with cwd %s" % (extension_path, args, cwd))
    returncode = ext.run(extension_path, args, cwd, os.environ)

    if returncode == 0:
        ext_logger.info('succeeded')
    else:
        for line in errors:
            ext_logger.error(line)
        message = '%s failed with code %s: %s' % (
            filename, returncode, '\n'.join(errors))
        raise BaserockImportException(message)

    return '\n'.join(output)


class ImportLoop(object):
    '''Import a package and all of its dependencies into Baserock.

    This class holds the state for the processing loop.

    '''

    def __init__(self, app, goal_kind, goal_name, goal_version, extra_args=[]):
        self.app = app
        self.goal_kind = goal_kind
        self.goal_name = goal_name
        self.goal_version = goal_version
        self.extra_args = extra_args

        self.lorry_set = baserockimport.lorryset.LorrySet(
            self.app.settings['lorries-dir'])
        self.morph_set = baserockimport.morphsetondisk.MorphologySetOnDisk(
            self.app.settings['definitions-dir'])

        self.morphloader = morphlib.morphloader.MorphologyLoader()

        self.importers = {}

    def enable_importer(self, kind, extra_args=[]):
        assert kind not in self.importers
        self.importers[kind] = {
            'extra_args': extra_args
        }

    def run(self):
        '''Process the goal package and all of its dependencies.'''
        start_time = time.time()
        start_displaytime = time.strftime('%x %X %Z', time.localtime())

        self.app.status(
            '%s: Import of %s %s started', start_displaytime, self.goal_kind,
            self.goal_name)

        if not self.app.settings['update-existing']:
            self.app.status(
                'Not updating existing Git checkouts or existing definitions')

        chunk_dir = os.path.join(self.morph_set.path, 'strata', self.goal_name)
        if not os.path.exists(chunk_dir):
            os.makedirs(chunk_dir)

        goal = baserockimport.package.Package(
            self.goal_kind, self.goal_name, self.goal_version)
        to_process = [goal]
        processed = networkx.DiGraph()

        errors = {}

        while len(to_process) > 0:
            current_item = to_process.pop()

            try:
                self._process_package(current_item)
                error = False
            except BaserockImportException as e:
                self.app.status(str(e), error=True)
                errors[current_item] = e
                error = True

            processed.add_node(current_item)

            if not error:
                self._process_dependencies(
                    current_item, current_item.dependencies, to_process,
                    processed)

        if len(errors) > 0:
            self.app.status(
                '\nErrors encountered, not generating a stratum morphology.')
            self.app.status(
                'See the README files for guidance.')
        else:
            self._generate_stratum_morph_if_none_exists(
                processed, self.goal_name)

        duration = time.time() - start_time
        end_displaytime = time.strftime('%x %X %Z', time.localtime())

        self.app.status(
            '%s: Import of %s %s ended (took %i seconds)', end_displaytime,
            self.goal_kind, self.goal_name, duration)

    def _process_package(self, package):
        kind = package.kind
        name = package.name
        version = package.version

        lorry = self._find_or_create_lorry_file(kind, name)
        source_repo, url = self._fetch_or_update_source(lorry)

        checked_out_version, ref = self._checkout_source_version(
            source_repo, name, version)
        package.set_version_in_use(checked_out_version)

        chunk_morph = self._find_or_create_chunk_morph(
            kind, name, checked_out_version, source_repo, url, ref)

        if self.app.settings['use-local-sources']:
            chunk_morph.repo_url = 'file://' + source_repo.dirname
        else:
            reponame = lorry.keys()[0]
            chunk_morph.repo_url = 'upstream:%s' % reponame

        package.set_morphology(chunk_morph)

        dependencies = self._find_or_create_dependency_list(
            kind, name, checked_out_version, source_repo)

        package.set_dependencies(dependencies)

    def _process_dependencies(self, current_item, dependencies, to_process,
                              processed):
        '''Enqueue all dependencies of a package that are yet to be processed.

        '''
        for key, value in dependencies.iteritems():
            kind = key

            self._process_dependency_list(
                current_item, kind, value['build-dependencies'], to_process,
                processed, True)
            self._process_dependency_list(
                current_item, kind, value['runtime-dependencies'], to_process,
                processed, False)

    def _process_dependency_list(self, current_item, kind, deps, to_process,
                                 processed, these_are_build_deps):
        # All deps are added as nodes to the 'processed' graph. Runtime
        # dependencies only need to appear in the stratum, but build
        # dependencies have ordering constraints, so we add edges in
        # the graph for build-dependencies too.

        for dep_name, dep_version in deps.iteritems():
            dep_package = find(
                processed, lambda i: i.match(dep_name, dep_version))

            if dep_package is None:
                # Not yet processed
                queue_item = find(
                    to_process, lambda i: i.match(dep_name, dep_version))
                if queue_item is None:
                    queue_item = baserockimport.package.Package(
                        kind, dep_name, dep_version)
                    to_process.append(queue_item)
                dep_package = queue_item

            dep_package.add_required_by(current_item)

            if these_are_build_deps or current_item.is_build_dep:
                # A runtime dep of a build dep becomes a build dep
                # itself.
                dep_package.set_is_build_dep(True)
                processed.add_edge(dep_package, current_item)

    def _find_or_create_lorry_file(self, kind, name):
        # Note that the lorry file may already exist for 'name', but lorry
        # files are named for project name rather than package name. In this
        # case we will generate the lorry, and try to add it to the set, at
        # which point LorrySet will notice the existing one and merge the two.
        lorry = self.lorry_set.find_lorry_for_package(kind, name)

        if lorry is None:
            lorry = self._generate_lorry_for_package(kind, name)

            if len(lorry) != 1:
                raise Exception(
                    'Expected generated lorry file with one entry.')

            lorry_filename = lorry.keys()[0]

            if '/' in lorry_filename:
                # We try to be a bit clever and guess that if there's a prefix
                # in the name, e.g. 'ruby-gems/chef' then it should go in a
                # mega-lorry file, such as ruby-gems.lorry.
                parts = lorry_filename.split('/', 1)
                lorry_filename = parts[0]

            if lorry_filename == '':
                raise cliapp.AppException(
                    'Invalid lorry data for %s: %s' % (name, lorry))

            self.lorry_set.add(lorry_filename, lorry)
        else:
            lorry_filename = lorry.keys()[0]
            logging.info(
                'Found existing lorry file for %s: %s', name, lorry_filename)

        return lorry

    def _generate_lorry_for_package(self, kind, name):
        tool = '%s.to_lorry' % kind
        if kind not in self.importers:
            raise Exception('Importer for %s was not enabled.' % kind)
        extra_args = self.importers[kind]['extra_args']
        self.app.status('Calling %s to generate lorry for %s', tool, name)
        lorry_text = run_extension(tool, extra_args + [name])
        try:
            lorry = json.loads(lorry_text)
        except ValueError:
            raise cliapp.AppException(
                'Invalid output from %s: %s' % (tool, lorry_text))
        return lorry

    def _run_lorry(self, lorry):
        f = tempfile.NamedTemporaryFile(delete=False)
        try:
            logging.debug(json.dumps(lorry))
            json.dump(lorry, f)
            f.close()
            cliapp.runcmd([
                'lorry', '--working-area',
                self.app.settings['lorry-working-dir'], '--pull-only',
                '--bundle', 'never', '--tarball', 'never', f.name])
        finally:
            os.unlink(f.name)

    def _fetch_or_update_source(self, lorry):
        assert len(lorry) == 1
        lorry_name, lorry_entry = lorry.items()[0]

        url = lorry_entry['url']
        reponame = '_'.join(lorry_name.split('/'))
        repopath = os.path.join(
            self.app.settings['lorry-working-dir'], reponame, 'git')

        checkoutpath = os.path.join(
            self.app.settings['checkouts-dir'], reponame)

        try:
            already_lorried = os.path.exists(repopath)
            if already_lorried:
                if self.app.settings['update-existing']:
                    self.app.status('Updating lorry of %s', url)
                    self._run_lorry(lorry)
            else:
                self.app.status('Lorrying %s', url)
                self._run_lorry(lorry)

            if os.path.exists(checkoutpath):
                repo = GitDirectory(checkoutpath)
                repo.update_remotes()
            else:
                if already_lorried:
                    logging.warning(
                        'Expected %s to exist, but will recreate it',
                        checkoutpath)
                cliapp.runcmd(['git', 'clone', repopath, checkoutpath])
                repo = GitDirectory(checkoutpath)
        except cliapp.AppException as e:
            raise BaserockImportException(e.msg.rstrip())

        return repo, url

    def _checkout_source_version(self, source_repo, name, version):
        # FIXME: we need to be a bit smarter than this. Right now we assume
        # that 'version' is a valid Git ref.

        possible_names = [
            version,
            'v%s' % version,
            '%s-%s' % (name, version)
        ]

        for tag_name in possible_names:
            if source_repo.has_ref(tag_name):
                source_repo.checkout(tag_name)
                ref = tag_name
                break
        else:
            if self.app.settings['use-master-if-no-tag']:
                logging.warning(
                    "Couldn't find tag %s in repo %s. Using 'master'.",
                    tag_name, source_repo)
                source_repo.checkout('master')
                ref = version = 'master'
            else:
                raise BaserockImportException(
                    'Could not find ref for %s version %s.' % (name, version))

        return version, ref

    def _find_or_create_chunk_morph(self, kind, name, version, source_repo,
                                    repo_url, named_ref):
        morphology_filename = 'strata/%s/%s-%s.morph' % (
            self.goal_name, name, version)
        sha1 = source_repo.resolve_ref_to_commit(named_ref)

        def generate_morphology():
            morphology = self._generate_chunk_morph_for_package(
                source_repo, kind, name, version, morphology_filename)
            self.morph_set.save_morphology(morphology_filename, morphology)
            return morphology

        if self.app.settings['update-existing']:
            morphology = generate_morphology()
        else:
            morphology = self.morph_set.get_morphology(
                repo_url, sha1, morphology_filename)

            if morphology is None:
                # Existing chunk morphologies loaded from disk don't contain
                # the repo and ref information. That's stored in the stratum
                # morph. So the first time we touch a chunk morph we need to
                # set this info.
                logging.debug("Didn't find morphology for %s|%s|%s", repo_url,
                              sha1, morphology_filename)
                morphology = self.morph_set.get_morphology(
                    None, None, morphology_filename)

                if morphology is None:
                    logging.debug("Didn't find morphology for None|None|%s",
                                  morphology_filename)
                    morphology = generate_morphology()

        morphology.repo_url = repo_url
        morphology.ref = sha1
        morphology.named_ref = named_ref

        return morphology

    def _generate_chunk_morph_for_package(self, source_repo, kind, name,
                                          version, filename):
        tool = '%s.to_chunk' % kind

        if kind not in self.importers:
            raise Exception('Importer for %s was not enabled.' % kind)
        extra_args = self.importers[kind]['extra_args']

        self.app.status(
            'Calling %s to generate chunk morph for %s %s', tool, name,
            version)

        args = extra_args + [source_repo.dirname, name]
        if version != 'master':
            args.append(version)
        text = run_extension(tool, args)

        return self.morphloader.load_from_string(text, filename)

    def _find_or_create_dependency_list(self, kind, name, version,
                                        source_repo):
        depends_filename = 'strata/%s/%s-%s.foreign-dependencies' % (
            self.goal_name, name, version)
        depends_path = os.path.join(
            self.app.settings['definitions-dir'], depends_filename)

        def calculate_dependencies():
            dependencies = self._calculate_dependencies_for_package(
                source_repo, kind, name, version, depends_path)
            with open(depends_path, 'w') as f:
                json.dump(dependencies, f)
            return dependencies

        if self.app.settings['update-existing']:
            dependencies = calculate_dependencies()
        elif os.path.exists(depends_path):
            with open(depends_path) as f:
                dependencies = json.load(f)
        else:
            logging.debug("Didn't find %s", depends_path)
            dependencies = calculate_dependencies()

        return dependencies

    def _calculate_dependencies_for_package(self, source_repo, kind, name,
                                            version, filename):
        tool = '%s.find_deps' % kind

        if kind not in self.importers:
            raise Exception('Importer for %s was not enabled.' % kind)
        extra_args = self.importers[kind]['extra_args']

        self.app.status(
            'Calling %s to calculate dependencies for %s %s', tool, name,
            version)

        args = extra_args + [source_repo.dirname, name]
        if version != 'master':
            args.append(version)
        text = run_extension(tool, args)

        return json.loads(text)

    def _sort_chunks_by_build_order(self, graph):
        order = reversed(sorted(graph.nodes()))
        try:
            return networkx.topological_sort(graph, nbunch=order)
        except networkx.NetworkXUnfeasible:
            # Cycle detected!
            loop_subgraphs = networkx.strongly_connected_component_subgraphs(
                graph, copy=False)
            all_loops_str = []
            for graph in loop_subgraphs:
                if graph.number_of_nodes() > 1:
                    loops_str = '->'.join(str(node) for node in graph.nodes())
                    all_loops_str.append(loops_str)
            raise cliapp.AppException(
                'One or more cycles detected in build graph: %s' %
                (', '.join(all_loops_str)))

    def _generate_stratum_morph_if_none_exists(self, graph, goal_name):
        filename = os.path.join(
            self.app.settings['definitions-dir'], 'strata', '%s.morph' %
            goal_name)

        if os.path.exists(filename):
            if not self.app.settings['update-existing']:
                self.app.status(
                    msg='Found stratum morph for %s at %s, not overwriting' %
                    (goal_name, filename))
                return

        self.app.status(msg='Generating stratum morph for %s' % goal_name)

        chunk_entries = []

        for package in self._sort_chunks_by_build_order(graph):
            m = package.morphology
            if m is None:
                raise cliapp.AppException('No morphology for %s' % package)

            def format_build_dep(name, version):
                dep_package = find(graph, lambda p: p.match(name, version))
                return '%s-%s' % (name, dep_package.version_in_use)

            build_depends = [
                format_build_dep(name, version) for name, version in
                m['x-build-dependencies-rubygems'].iteritems()
            ]

            entry = {
                'name': m['name'],
                'repo': m.repo_url,
                'ref': m.ref,
                'unpetrify-ref': m.named_ref,
                'morph': m.filename,
                'build-depends': build_depends,
            }
            chunk_entries.append(entry)

        stratum_name = goal_name
        stratum = {
            'name': stratum_name,
            'kind': 'stratum',
            'description': 'Autogenerated by Baserock import tool',
            'build-depends': [
                {'morph': 'strata/ruby.morph'}
            ],
            'chunks': chunk_entries,
        }

        morphology = self.morphloader.load_from_string(
            json.dumps(stratum), filename=filename)
        self.morphloader.unset_defaults(morphology)
        self.morphloader.save_to_file(filename, morphology)
