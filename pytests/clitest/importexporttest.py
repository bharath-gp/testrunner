import copy
import json, filecmp
import os, shutil, ast
from threading import Thread

from membase.api.rest_client import RestConnection
from memcached.helper.data_helper import MemcachedClientHelper
from TestInput import TestInputSingleton
from clitest.cli_base import CliBaseTest
from remote.remote_util import RemoteMachineShellConnection
from membase.helper.bucket_helper import BucketOperationHelper
from membase.helper.cluster_helper import ClusterOperationHelper
from couchbase_cli import CouchbaseCLI
from pprint import pprint
from testconstants import CLI_COMMANDS, COUCHBASE_FROM_WATSON,\
                          COUCHBASE_FROM_SPOCK, LINUX_COUCHBASE_BIN_PATH,\
                          WIN_COUCHBASE_BIN_PATH, COUCHBASE_FROM_SHERLOCK


class ImportExportTests(CliBaseTest):
    def setUp(self):
        super(ImportExportTests, self).setUp()

    def tearDown(self):
        super(ImportExportTests, self).tearDown()
        if self.import_back:
            self.info("clean up server in import back tests")
            imp_servers = copy.deepcopy(self.servers[2:])
            BucketOperationHelper.delete_all_buckets_or_assert(imp_servers, self)
            ClusterOperationHelper.cleanup_cluster(self.servers, imp_servers[0])
            ClusterOperationHelper.wait_for_ns_servers_or_assert(imp_servers, self)


    def test_export_from_empty_bucket(self):
        options = {"load_doc": False, "bucket":"empty"}
        return self._common_imex_test("export", options)

    def test_export_from_sasl_bucket(self):
        options = {"load_doc": True, "docs":"1000"}
        return self._common_imex_test("export", options)

    def test_export_and_import_back(self):
        options = {"load_doc": True, "docs":"10"}
        return self._common_imex_test("export", options)

    def _common_imex_test(self, cmd, options):
        username = self.input.param("username", None)
        password = self.input.param("password", None)
        path = self.input.param("path", None)
        self.imex_type = self.input.param("imex_type", None)
        self.format_type = self.input.param("format_type", None)
        self.ex_path = self.tmp_path + "export/"
        master = self.servers[0]
        server = copy.deepcopy(master)

        if username is None:
            username = server.rest_username
        if password is None:
            password = server.rest_password
        if path is None:
            self.log.info("test with absolute path ")
        elif path == "local":
            self.log.info("test with local bin path ")
            self.cli_command_path = "cd %s; ./" % self.cli_command_path
        self.buckets = RestConnection(server).get_buckets()
        if "export" in cmd:
            cmd = "cbexport"
            if options["load_doc"]:
                if len(self.buckets) >= 1:
                    for bucket in self.buckets:
                        self.log.info("load json to bucket %s " % bucket.name)
                        load_cmd = "%s%s%s -n %s:8091 -u %s -p %s -j -i %s -b %s "\
                            % (self.cli_command_path, "cbworkloadgen", self.cmd_ext,
                               server.ip, username, password, options["docs"],
                               bucket.name)
                        self.shell.execute_command(load_cmd)
            """ remove previous export directory at tmp dir and re-create it
                in linux:   /tmp/export
                in windows: /cygdrive/c/tmp/export """
            self.shell.execute_command("rm -rf %sexport " % self.tmp_path)
            self.shell.execute_command("mkdir %sexport " % self.tmp_path)
            """ /opt/couchbase/bin/cbexport json -c localhost -u Administrator 
                              -p password -b default -f list -o /tmp/test4.zip """
            if len(self.buckets) >= 1:
                for bucket in self.buckets:
                    export_file = self.ex_path + bucket.name
                    exe_cmd_str = "%s%s%s %s -c %s -u %s -p %s -b %s -f %s -o %s"\
                         % (self.cli_command_path, cmd, self.cmd_ext, self.imex_type,
                                     server.ip, username, password, bucket.name,
                                                    self.format_type, export_file)
                    output, error = self.shell.execute_command(exe_cmd_str)
                    self._verify_export_file(bucket.name, options)

            if self.import_back:
                import_file = export_file
                import_servers = copy.deepcopy(self.servers)
                imp_rest = RestConnection(import_servers[2])
                import_shell = RemoteMachineShellConnection(import_servers[2])
                imp_rest.force_eject_node()
                self.sleep(2)
                imp_rest = RestConnection(import_servers[2])
                status = False
                info = imp_rest.get_nodes_self()
                if info.memoryQuota and int(info.memoryQuota) > 0:
                    print "info  ", info.memoryQuota
                    self.quota = info.memoryQuota
                imp_rest.init_node()
                self.cluster.rebalance(import_servers[2:], [import_servers[3]], [])
                self.cluster.create_default_bucket(import_servers[2], "250", self.num_replicas,
                                               enable_replica_index=self.enable_replica_index,
                                               eviction_policy=self.eviction_policy)
                imp_cmd_str = "%s%s%s %s -c %s -u %s -p %s -b %s -d file://%s -f %s -g %s"\
                              % (self.cli_command_path, "cbimport", self.cmd_ext, self.imex_type,
                                 import_servers[2].ip, username, password, "default",
                                 import_file, self.format_type, "index")
                output, error = self.import_shell.execute_command(imp_cmd_str)
                if self._check_output("error", output):
                    self.fail("Fail to run import back to bucket")
                

    def _verify_export_file(self, export_file_name, options):
        if not options["load_doc"]:
            if "bucket" in options and options["bucket"] == "empty":
                output, error = self.shell.execute_command("ls %s" % self.ex_path)
                if export_file_name in output[0]:
                    self.log.info("check if export file %s is empty" % export_file_name)
                    output, error = self.shell.execute_command("cat %s%s"\
                                                 % (self.ex_path, export_file_name))
                    if output:
                        self.fail("file %s should be empty" % export_file_name)
                else:
                    self.fail("Fail to export.  File %s does not exist" \
                                                            % export_file_name)
        elif options["load_doc"]:
            found = self.shell.file_exists(self.ex_path, export_file_name)
            if found:
                self.log.info("copy export file from remote to local")
                if os.path.exists("/tmp/export"):
                    shutil.rmtree("/tmp/export")
                os.makedirs("/tmp/export")
                self.shell.copy_file_remote_to_local(self.ex_path+export_file_name,\
                                                    "/tmp/export/"+export_file_name)
                self.log.info("compare 2 json files")
                if self.format_type == "lines":
                    sample_file = open("resources/imex/json_%s_lines" % options["docs"])
                    samples = sample_file.readlines()
                    export_file = open("/tmp/export/"+ export_file_name)
                    exports = export_file.readlines()
                    if sorted(samples) == sorted(exports):
                        self.log.info("export and sample json mathch")
                    else:
                        self.fail("export and sample json does not match")
                    sample_file.close()
                    export_file.close()
                elif self.format_type == "list":
                    sample_file = open("resources/imex/json_list_%s_lines" % options["docs"])
                    samples = sample_file.read()
                    samples = ast.literal_eval(samples)
                    samples.sort(key=lambda k: k['name'])
                    export_file = open("/tmp/export/"+ export_file_name)
                    exports = export_file.read()
                    exports = ast.literal_eval(exports)
                    exports.sort(key=lambda k: k['name'])
                    print "sample  ", samples
                    print "export  ", exports
                    if samples == exports:
                        self.log.info("export and sample json files are matched")
                    else:
                        self.fail("export and sample json files did not match")
                    sample_file.close()
                    export_file.close()
            else:
                self.fail("There is not export file in %s%s"\
                                  % (self.ex_path, export_file_name))

    def _check_output(self, word_check, output):
        found = False
        if len(output) >=1 :
            for x in output:
                if word_check.lower() in x.lower():
                    self.log.info("Found \"%s\" in CLI output" % word_check)
                    found = True
        return found
