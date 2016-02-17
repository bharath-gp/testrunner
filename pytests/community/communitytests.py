import json
import time
import unittest
import testconstants
from TestInput import TestInputSingleton

from community.community_base import CommunityBaseTest
from community.community_base import CommunityXDCRBaseTest
from memcached.helper.data_helper import  MemcachedClientHelper
from membase.api.rest_client import RestConnection, Bucket
from membase.helper.rebalance_helper import RebalanceHelper
from membase.api.exception import RebalanceFailedException
from couchbase_helper.documentgenerator import BlobGenerator
from remote.remote_util import RemoteMachineShellConnection
from membase.helper.cluster_helper import ClusterOperationHelper
from scripts.install import InstallerJob
from testconstants import SHERLOCK_VERSION
from testconstants import WATSON_VERSION




class CommunityTests(CommunityBaseTest):
    def setUp(self):
        super(CommunityTests, self).setUp()
        self.command = self.input.param("command", "")
        self.zone = self.input.param("zone", 1)
        self.replica = self.input.param("replica", 1)
        self.command_options = self.input.param("command_options", '')
        self.set_get_ratio = self.input.param("set_get_ratio", 0.9)
        self.item_size = self.input.param("item_size", 128)
        self.shutdown_zone = self.input.param("shutdown_zone", 1)
        self.do_verify = self.input.param("do-verify", True)
        self.num_node = self.input.param("num_node", 4)
        self.services = self.input.param("services", None)
        self.start_node_services = self.input.param("start_node_services", "kv")
        self.add_node_services = self.input.param("add_node_services", "kv")
        self.timeout = 6000


    def tearDown(self):
        super(CommunityTests, self).tearDown()

    def test_disabled_zone(self):
        disabled_zone = False
        zone_name = "group1"
        serverInfo = self.servers[0]
        rest = RestConnection(serverInfo)
        try:
            self.log.info("create zone name 'group1'!")
            result = rest.add_zone(zone_name)
            print "result  ",result
        except Exception, e :
            if e:
                print e
                disabled_zone = True
                pass
        if not disabled_zone:
            self.fail("CE version should not have zone feature")

    def check_audit_available(self):
        audit_available = False
        self.rest = RestConnection(self.master)
        try:
            self.rest.getAuditSettings()
            audit_available = True
        except Exception, e :
            if e:
                print e
        if audit_available:
            self.fail("This feature 'audit' only available on "
                      "Enterprise Edition")

    def check_ldap_available(self):
        ldap_available = False
        self.rest = RestConnection(self.master)
        try:
            s, c, h = self.rest.clearLDAPSettings()
            if s:
                ldap_available = True
        except Exception, e :
            if e:
                print e
        if ldap_available:
            self.fail("This feature 'ldap' only available on "
                      "Enterprise Edition")

    def check_set_services(self):
        self.rest = RestConnection(self.master)
        self.rest.force_eject_node()
        self.sleep(7, "wait for node reset done")
        try:
            status = self.rest.init_node_services(hostname=self.master.ip,
                                                 services=[self.services])
        except Exception, e:
            if e:
                print e
        if self.services == "kv":
            if status:
                self.log.info("CE could set {0} only service."
                                  .format(self.services))
            else:
                self.fail("Failed to set {0} only service."
                                   .format(self.services))
        elif self.services == "index,kv":
            if status:
                self.fail("CE does not support kv and index on same node")
            else:
                self.log.info("services enforced in CE")
        elif self.services == "kv,n1ql":
            if status:
                self.fail("CE does not support kv and n1ql on same node")
            else:
                self.log.info("services enforced in CE")
        elif self.services == "index,n1ql":
            if status:
                self.fail("CE does not support index and n1ql on same node")
            else:
                self.log.info("services enforced in CE")
        elif self.services == "index,kv,n1ql":
            if self.version not in WATSON_VERSION:
                if status:
                    self.log.info("CE could set all services {0} on same nodes."
                                                           .format(self.services))
                else:
                    self.fail("Failed to set kv, index and query services on CE")
            elif self.version in WATSON_VERSION:
                if status:
                    self.fail("CE does not support only"
                              " kv, index and n1ql on same node")
                else:
                    self.log.info("services enforced in CE")
        elif self.version in WATSON_VERSION:
            if self.services == "index,kv,fts":
                if status:
                    self.fail("CE does not support kv, index and fts on same node")
                else:
                    self.log.info("services enforced in CE")
            elif self.services == "index,n1ql,fts":
                if status:
                    self.fail("CE does not support index, n1ql and fts on same node")
                else:
                    self.log.info("services enforced in CE")
            elif self.services == "kv,n1ql,fts":
                if status:
                    self.fail("CE does not support kv, n1ql and fts on same node")
                else:
                    self.log.info("services enforced in CE")
            elif self.services == "kv,index,n1ql,fts":
                if status:
                    self.log.info("CE could set all services {0} on same nodes."
                                                           .format(self.services))
                else:
                    self.fail("Failed to set "
                              "kv, index, query and fts services on CE")
        else:
            self.fail("some services don't support")

    def check_set_services_when_add_node(self):
        self.rest = RestConnection(self.master)
        self.rest.force_eject_node()
        sherlock_services_in_ce = ["kv", "index,kv,n1ql"]
        watson_services_in_ce = ["kv", "index,kv,n1ql,fts"]
        self.sleep(5, "wait for node reset done")
        try:
            self.log.info("Initialize node with services {0}"
                                  .format(self.start_node_services))
            status = self.rest.init_node_services(hostname=self.master.ip,
                                        services=[self.start_node_services])
            init_node = self.cluster.async_init_node(self.master,
                                            services = [self.start_node_services])
        except Exception, e:
            if e:
                print e
        if not status:
            if self.version not in WATSON_VERSION and \
                         self.start_node_services not in sherlock_services_in_ce:
                self.log.info("services setting enforced in Sherlock CE")
            elif self.version in WATSON_VERSION and \
                         self.start_node_services not in watson_services_in_ce:
                self.log.info("services setting enforced in Watson CE")

        if status and init_node.result() != 0:
            add_node = False
            try:
                self.log.info("node with services {0} try to add"
                                  .format(self.add_node_services))
                add_node = self.cluster.rebalance(self.servers[:2],
                                                  self.servers[1:2], [],
                                      services = [self.add_node_services])
            except Exception:
                pass
            if add_node:
                self.get_services_map()
                list_nodes = self.get_nodes_from_services_map(get_all_nodes=True)
                map = self.get_nodes_services()
                if map[self.master.ip] == self.start_node_services and \
                    map[self.servers[1].ip] == self.add_node_services:
                    self.log.info("services set correctly when node added & rebalance")
                else:
                    self.fail("services set incorrectly when node added & rebalance")
            else:
                if self.verison not in WATSON_VERSION:
                    if self.start_node_services in ["kv", "index,kv,n1ql"] and \
                          self.add_node_services not in ["kv", "index,kv,n1ql"]:
                        self.log.info("services are enforced in CE")
                    elif self.start_node_services not in ["kv", "index,kv,n1ql"]:
                        self.log.info("services are enforced in CE")
                    else:
                        self.fail("maybe bug in add node")
                elif self.version in WATSON_VERSION:
                    if self.start_node_services in ["kv", "index,kv,n1ql,fts"] and \
                          self.add_node_services not in ["kv", "index,kv,n1ql,fts"]:
                        self.log.info("services are enforced in CE")
                    elif self.start_node_services not in ["kv", "index,kv,n1ql,fts"]:
                        self.log.info("services are enforced in CE")
                    else:
                        self.fail("maybe bug in add node")
        else:
            self.fail("maybe bug in node initialization")

    def check_full_backup_only(self):
        """ for windows vm, ask IT to put uniq.exe at
            /cygdrive/c/Program Files (x86)/ICW/bin directory """

        shell = RemoteMachineShellConnection(self.master)
        """ put params items=0 in test param so that init items = 0 """
        shell.execute_command("{0}cbworkloadgen -n {1}:8091 -j -i 1000"
                                            .format(self.bin_path, self.master.ip))
        """ delete backup location before run backup """
        shell.execute_command("rm -rf {0}*".format(self.backup_location))
        output, error = shell.execute_command("ls -lh {0}"
                                                     .format(self.backup_location))
        shell.log_command_output(output, error)

        """ first full backup """
        shell.execute_command("{0}cbbackup http://{1}:8091 {2} -m full"
                .format(self.bin_path, self.master.ip, self.backup_location))
        output, error = shell.execute_command("ls -lh {0}*/"
                                        .format(self.backup_location))
        shell.log_command_output(output, error)
        output, error = shell.execute_command("{0}cbtransfer {1}*/*-full/ stdout: \
                                                         | grep set | uniq | wc -l"
                                      .format(self.bin_path, self.backup_location))
        shell.log_command_output(output, error)
        if int(output[0]) != 1000:
            self.fail("full backup did not work in CE. "
                      "Expected 1000, actual: {0}".format(output[0]))
        shell.execute_command("{0}cbworkloadgen -n {1}:8091 -j -i 1000 --prefix=t_"
                                            .format(self.bin_path, self.master.ip))
        """ do different backup mode """
        shell.execute_command("{0}cbbackup http://{1}:8091 {2} -m {3}"
                       .format(self.bin_path, self.master.ip, self.backup_location,
                                                               self.backup_option))
        output, error = shell.execute_command("ls -lh {0}"
                                                     .format(self.backup_location))
        shell.log_command_output(output, error)
        output, error = shell.execute_command("{0}cbtransfer {1}*/*-{2}/ stdout: \
                                                         | grep set | uniq | wc -l"
                                       .format(self.bin_path, self.backup_location,
                                                               self.backup_option))
        shell.log_command_output(output, error)
        if int(output[0]) == 2000:
            self.log.info("backup option 'diff' is enforced in CE")
        elif int(output[0]) == 1000:
            self.fail("backup option 'diff' is not enforced in CE. "
                      "Expected 2000, actual: {0}".format(output[0]))
        else:
            self.fail("backup failed to backup correct items")


class CommunityXDCRTests(CommunityXDCRBaseTest):
    def setUp(self):
        super(CommunityXDCRTests, self).setUp()

    def tearDown(self):
        super(CommunityXDCRTests, self).tearDown()

    def test_xdcr_filter(self):
        filter_on = False
        serverInfo = self._servers[0]
        rest = RestConnection(serverInfo)
        rest.remove_all_replications()
        shell = RemoteMachineShellConnection(serverInfo)
        output, error = shell.execute_command('curl -X POST '
                                         '-u Administrator:password '
                     ' http://{0}:8091/controller/createReplication '
                     '-d fromBucket="default" '
                     '-d toCluster="cluster1" '
                     '-d toBucket="default" '
                     '-d replicationType="continuous" '
                     '-d filterExpression="some_exp"'
                                              .format(serverInfo.ip))
        if output:
            self.log.info(output[0])
        if output and "default" in output[0]:
            self.fail("XDCR Filter feature should not available in "
                      "Community Edition")