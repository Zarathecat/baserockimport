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


class BaserockImportException(cliapp.AppException):
    pass


def find(iterable, match):
    return next((x for x in iterable if match(x)), None)


def run_extension(filename, args):
    '''Run the import extension 'filename' with the given arguments.

    Returns the output written by the extension to its stdout.

    If the extension subprocess returns an
    error code (any value other than zero) then BaserockImportException will be
    raised, with the contents of stderr stored in its .message attribute.

    Note that the stdout and strerr processing expects each line to be
    terminated with '\n' (newline character). Any output beyond the last \n
    character will be ignored.

    '''
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
        return os.path.join(module_dir, 'exts')

    extension_path = os.path.join(extensions_dir(), filename)

    logging.debug("Running %s %s" % (extension_path, args))
    cwd = '.'
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

    def __init__(self, app, goal_kind, goal_name, goal_version):
        '''Set up an ImportLoop to process dependencies of one goal package.'''

        self.app = app
        self.goal_kind = goal_kind
        self.goal_name = goal_name
        self.goal_version = goal_version

        self.lorry_set = baserockimport.lorryset.LorrySet(
            self.app.settings['lorries-dir'])
        self.morph_set = baserockimport.morphsetondisk.MorphologySetOnDisk(
            self.app.settings['definitions-dir'])

        self.morphloader = morphlib.morphloader.MorphologyLoader()

        self.importers = {}

    def enable_importer(self, kind, extra_args=[]):
        '''Enable an importer extension in this ImportLoop instance.

        At least one importer extension must be enabled for the loop to do
        anything.

        Enabling more than one extension is handy for packaging systems which
        can list dependencies in other package universes: for example, Omnibus
        software components can depend on other Omnibus software components,
        but also on RubyGems.

        '''
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

        # Every Package object is added as a node in the 'processed' graph.
        # The set of nodes in graph corresponds to the set of packages needed
        # at runtime for the goal package to function. The edges in the graph
        # correspond to build-time dependencies between packages. This format
        # is convenient when we need to construct a suitable stratum morphology
        # for the goal package.
        processed = networkx.DiGraph()

        errors = {}

        # This is the main processing loop of an import!

        while len(to_process) > 0:
            current_item = to_process.pop()

            try:
                self._process_package(current_item)
                error = False
            except BaserockImportException as e:
                self.app.status('%s', e, error=True)
                errors[current_item] = e
                error = True

            if not error:
                self._update_queue_and_graph(
                    current_item, current_item.dependencies, to_process,
                    processed, errors)

        self._maybe_generate_stratum(processed, errors, self.goal_name)

        duration = time.time() - start_time
        end_displaytime = time.strftime('%x %X %Z', time.localtime())

        self.app.status(
            '%s: Import of %s %s ended (took %i seconds)', end_displaytime,
            self.goal_kind, self.goal_name, duration)

    def _process_package(self, package):
        '''Process a single package.'''

        kind = package.kind
        name = package.name
        version = package.version

        # 1. Make the source code available.

        lorry = self._find_or_create_lorry_file(kind, name)
        source_repo, url = self._fetch_or_update_source(lorry)

        checked_out_version, ref = self._checkout_source_version_for_package(
            source_repo, package)
        package.set_version_in_use(checked_out_version)

        repo_path = os.path.relpath(source_repo.dirname)
        if morphlib.git.is_valid_sha1(ref):
            self.app.status(
                "%s %s: using %s commit %s", name, version, repo_path, ref)
        else:
            self.app.status(
                "%s %s: using %s ref %s (commit %s)", name, version, repo_path,
                ref, source_repo.resolve_ref_to_commit(ref))

        # 2. Create a chunk morphology with build instructions.

        chunk_morph = self._find_or_create_chunk_morph(
            kind, name, checked_out_version, source_repo, url, ref)

        if self.app.settings['use-local-sources']:
            chunk_morph.repo_url = 'file://' + source_repo.dirname
        else:
            reponame = lorry.keys()[0]
            chunk_morph.repo_url = 'upstream:%s' % reponame

        package.set_morphology(chunk_morph)

        # 3. Calculate the dependencies of this package.

        dependencies = self._find_or_create_dependency_list(
            kind, name, checked_out_version, source_repo)

        package.set_dependencies(dependencies)

    def _update_queue_and_graph(self, current_item, dependencies, to_process,
                                processed, errors):
        '''Mark current_item as processed and enqueue any new dependencies.'''

        processed.add_node(current_item)

        for kind, kind_deps in dependencies.iteritems():

            build_deps = kind_deps['build-dependencies']
            for name, version in build_deps.iteritems():
                self._update_queue_and_graph_with_dependency(
                    current_item, kind, name, version, True, to_process,
                    processed, errors)

            runtime_deps = kind_deps['runtime-dependencies']
            for name, version in runtime_deps.iteritems():
                self._update_queue_and_graph_with_dependency(
                    current_item, kind, name, version, False, to_process,
                    processed, errors)

    def _update_queue_and_graph_with_dependency(self, current_item, kind, name,
                                                version, is_build_dep,
                                                to_process, processed, errors):
        failed_dep_package = find(
            errors, lambda i: i.match(kind, name, version))
        if failed_dep_package:
            logging.debug(
                "Ignoring %s as it failed earlier.", failed_dep_package)
            return

        dep_package = find(
            processed, lambda i: i.match(kind, name, version))

        if dep_package is None:
            # Not yet processed
            queue_item = find(
                to_process, lambda i: i.match(kind, name, version))
            if queue_item is None:
                queue_item = baserockimport.package.Package(
                    kind, name, version)
                to_process.append(queue_item)
            dep_package = queue_item

        dep_package.add_required_by(current_item)

        if is_build_dep or current_item.is_build_dep:
            # A runtime dep of a build dep becomes a build dep itself.
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
        self.app.status(
            '%s: calling %s to generate lorry', name, tool)
        lorry_text = run_extension(tool, extra_args + [name])
        try:
            lorry = json.loads(lorry_text)
        except ValueError:
            raise cliapp.AppException(
                'Invalid output from %s: %s' % (tool, lorry_text))
        return lorry

    def _run_lorry(self, lorry):
        with tempfile.NamedTemporaryFile() as f:
            logging.debug(json.dumps(lorry))
            json.dump(lorry, f)
            f.flush()
            cliapp.runcmd([
                'lorry', '--working-area',
                self.app.settings['lorry-working-dir'], '--pull-only',
                '--bundle', 'never', '--tarball', 'never', f.name])

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
                repo = morphlib.gitdir.GitDirectory(checkoutpath)
                repo.update_remotes()
            else:
                if already_lorried:
                    logging.warning(
                        'Expected %s to exist, but will recreate it',
                        checkoutpath)
                cliapp.runcmd(['git', 'clone', repopath, checkoutpath])
                repo = morphlib.gitdir.GitDirectory(checkoutpath)
        except cliapp.AppException as e:
            raise BaserockImportException(e.msg.rstrip())

        return repo, url

    def _checkout_source_version_for_package(self, source_repo, package):
        # FIXME: we need to be a bit smarter than this. Right now we assume
        # that 'version' is a valid Git ref.
        name = package.name
        version = package.version

        possible_names = [
            version,
            'v%s' % version,
            '%s-%s' % (name, version)
        ]

        for tag_name in possible_names:
            if source_repo.ref_exists(tag_name):
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
                    'Could not find ref for %s.' % package)

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
            '%s %s: calling %s to generate chunk morph', name, version, tool)

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
            '%s %s: calling %s to calculate dependencies', name, version, tool)

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

    def _maybe_generate_stratum(self, graph, errors, goal_name):
        filename = os.path.join(
            self.app.settings['definitions-dir'], 'strata', '%s.morph' %
            goal_name)
        update_existing = self.app.settings['update-existing']

        if self.app.settings['force-stratum-generation']:
            self._generate_stratum(
                graph, goal_name, filename, ignore_errors=True)
        elif len(errors) > 0:
            self.app.status(
                '\nErrors encountered, not generating a stratum morphology.')
            self.app.status(
                'See the README files for guidance.')
        elif os.path.exists(filename) and not update_existing:
            self.app.status(
                msg='Found stratum morph for %s at %s, not overwriting' %
                (goal_name, filename))
        else:
            self._generate_stratum(graph, goal_name, filename)

    def _generate_stratum(self, graph, goal_name, filename,
                          ignore_errors=False):
        self.app.status(msg='Generating stratum morph for %s' % goal_name)

        chunk_entries = []

        for package in self._sort_chunks_by_build_order(graph):
            m = package.morphology

            if m is None:
                if ignore_errors:
                    logging.warn(
                        'Ignoring %s because there is no chunk morphology.')
                    continue
                else:
                    raise cliapp.AppException('No morphology for %s' % package)

            def format_build_dep(kind, name, version):
                dep_package = find(
                    graph, lambda p: p.match(kind, name, version))
                return '%s-%s' % (name, dep_package.version_in_use)

            def get_build_deps(morphology, kind):
                field = 'x-build-dependencies-%s' % kind
                return morphology.get(field, {})

            build_depends = []
            for kind in self.importers:
                for name, version in get_build_deps(m, kind).iteritems():
                    build_depends.extend(
                        format_build_dep(kind, name, version))

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

        morphology = morphlib.morphology.Morphology(stratum)
        morphology.filename = filename
        self.morphloader.save_to_file(filename, morphology)
