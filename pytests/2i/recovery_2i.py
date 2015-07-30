from remote.remote_util import RemoteMachineShellConnection
from membase.api.rest_client import RestConnection
from couchbase_helper.query_definitions import QueryDefinition
from membase.helper.cluster_helper import ClusterOperationHelper
from base_2i import BaseSecondaryIndexingTests
import copy

class SecondaryIndexingRecoveryTests(BaseSecondaryIndexingTests):

    def setUp(self):
        self.use_replica =True
        self.all_index_nodes_lost = False
        super(SecondaryIndexingRecoveryTests, self).setUp()
        self.load_query_definitions = []
        self.initial_index_number = self.input.param("initial_index_number", 10)
        for x in range(1,self.initial_index_number):
            index_name = "index_name_"+str(x)
            query_definition = QueryDefinition(index_name=index_name, index_fields = ["join_mo"], \
                        query_template = "", groups = ["simple"])
            self.load_query_definitions.append(query_definition)
        find_index_lost_list = self._find_list_of_indexes_lost()
        self._create_replica_index_when_indexer_is_down(find_index_lost_list)
        self.initialize_multi_create_index(buckets = self.buckets,
                    query_definitions = self.load_query_definitions)
        self.drop_indexes_in_between = self.input.param("drop_indexes_in_between", False)

    def tearDown(self):
        if hasattr(self, 'query_definitions'):
            check = True
            try:
                self.log.info("<<<<<< WILL DROP THE INDEXES >>>>>")
                tasks = self.async_run_multi_operations(buckets = self.buckets, query_definitions = self.query_definitions)
                for task in tasks:
                    task.result()
                self.run_multi_operations(buckets = self.buckets, query_definitions = self.load_query_definitions)
            except Exception, ex:
                self.log.info(ex)
        super(SecondaryIndexingRecoveryTests, self).tearDown()

    def test_rebalance_in(self):
        try:
            self._run_initial_index_tasks()
            kvOps_tasks = self._run_kvops_tasks()
            before_index_ops = self._run_before_index_tasks()
            rebalance = self.cluster.async_rebalance(self.servers[:self.nodes_init],self.nodes_in_list, [], services = self.services_in)
            self.sleep(1)
            in_between_index_ops = self._run_in_between_tasks()
            rebalance.result()
            self._run_tasks([kvOps_tasks, before_index_ops, in_between_index_ops])
            self._run_after_index_tasks()
        except Exception, ex:
            raise

    def test_rebalance_out(self):
        try:
            self._run_initial_index_tasks()
            kvOps_tasks = self._run_kvops_tasks()
            before_index_ops = self._run_before_index_tasks()
            rebalance = self.cluster.async_rebalance(self.servers[:self.nodes_init],[],self.nodes_out_list)
            self.sleep(1)
            in_between_index_ops = self._run_in_between_tasks()
            self._run_tasks([kvOps_tasks, before_index_ops, in_between_index_ops])
            rebalance.result()
            self._run_after_index_tasks()
        except Exception, ex:
            raise

    def test_rebalance_in_out(self):
        try:
            self._run_initial_index_tasks()
            kvOps_tasks = self._run_kvops_tasks()
            before_index_ops = self._run_before_index_tasks()
            rebalance = self.cluster.async_rebalance(self.servers[:self.nodes_init],
                                    self.nodes_in_list,
                                   self.nodes_out_list, services = self.services_in)
            self.sleep(1)
            in_between_index_ops = self._run_in_between_tasks()
            rebalance.result()
            self._run_tasks([kvOps_tasks, before_index_ops, in_between_index_ops])
            self._run_after_index_tasks()
        except Exception, ex:
            raise

    def test_rebalance_with_stop_start(self):
        try:
            self._run_initial_index_tasks()
            kvOps_tasks = self._run_kvops_tasks()
            before_index_ops = self._run_before_index_tasks()
            rebalance = self.cluster.async_rebalance(self.servers[:self.nodes_init],
                                    self.nodes_in_list,
                                   self.nodes_out_list, services = self.services_in)
            stopped = RestConnection(self.master).stop_rebalance(wait_timeout=self.wait_timeout / 3)
            self.assertTrue(stopped, msg="unable to stop rebalance")
            rebalance.result()
            rebalance = self.cluster.async_rebalance(self.servers[:self.nodes_init],
                                    self.nodes_in_list,
                                   self.nodes_out_list, services = self.services_in)
            in_between_index_ops = self._run_in_between_tasks()
            rebalance.result()
            self._run_tasks([kvOps_tasks, before_index_ops, in_between_index_ops])
            self._run_after_index_tasks()
        except Exception, ex:
            raise

    def test_server_crash(self):
        try:
            self.use_replica=False
            self.targetProcess= self.input.param("targetProcess",'memcached')
            self._run_initial_index_tasks()
            kvOps_tasks = self._run_kvops_tasks()
            before_index_ops = self._run_before_index_tasks()
            for node in self.nodes_out_list:
                remote = RemoteMachineShellConnection(node)
                remote.terminate_process(process_name=self.targetProcess)
            in_between_index_ops = self._run_in_between_tasks()
            self._run_tasks([kvOps_tasks, before_index_ops, in_between_index_ops])
            self._run_after_index_tasks()
        except Exception, ex:
            raise

    def test_server_restart(self):
        try:
            self._run_initial_index_tasks()
            kvOps_tasks = self._run_kvops_tasks()
            before_index_ops = self._run_before_index_tasks()
            for node in self.nodes_out_list:
                remote = RemoteMachineShellConnection(node)
                remote.stop_server()
            self.sleep(1)
            in_between_index_ops = self._run_in_between_tasks()
            self._run_tasks([kvOps_tasks, before_index_ops, in_between_index_ops])
            self._run_after_index_tasks()
        except Exception, ex:
            raise
        finally:
            for node in self.nodes_out_list:
                remote = RemoteMachineShellConnection(node)
                remote.start_server()

    def test_failover(self):
        try:
            self._run_initial_index_tasks()
            servr_out = self.nodes_out_list
            kvOps_tasks = self._run_kvops_tasks()
            before_index_ops = self._run_before_index_tasks()
            failover_task = self.cluster.async_failover([self.master],
                    failover_nodes = servr_out, graceful=self.graceful)
            in_between_index_ops = self._run_in_between_tasks()
            failover_task.result()
            if self.graceful:
                # Check if rebalance is still running
                msg = "graceful failover failed for nodes"
                self.assertTrue(RestConnection(self.master).monitorRebalance(stop_if_loop=True), msg=msg)
            rebalance = self.cluster.async_rebalance(self.servers[:self.nodes_init],
                                   [], servr_out)
            rebalance.result()
            self._run_tasks([kvOps_tasks, before_index_ops, in_between_index_ops])
            self._run_after_index_tasks()
        except Exception, ex:
            raise

    def test_failover_add_back(self):
        try:
            rest = RestConnection(self.master)
            recoveryType = self.input.param("recoveryType", "full")
            servr_out = self.nodes_out_list
            nodes_all = rest.node_statuses()
            self._run_initial_index_tasks()
            failover_task =self.cluster.async_failover([self.master],
                    failover_nodes = servr_out, graceful=self.graceful)
            failover_task.result()
            kvOps_tasks = self._run_kvops_tasks()
            before_index_ops = self._run_before_index_tasks()
            nodes_all = rest.node_statuses()
            nodes = []
            if servr_out[0].ip == "127.0.0.1":
                for failover_node in servr_out:
                    nodes.extend([node for node in nodes_all
                        if (str(node.port) == failover_node.port)])
            else:
                for failover_node in servr_out:
                    nodes.extend([node for node in nodes_all
                        if node.ip == failover_node.ip])
            for node in nodes:
                self.log.info(node)
                rest.add_back_node(node.id)
                rest.set_recovery_type(otpNode=node.id, recoveryType=recoveryType)
            rebalance = self.cluster.async_rebalance(self.servers[:self.nodes_init], [], [])
            in_between_index_ops = self._run_in_between_tasks()
            rebalance.result()
            self._run_tasks([kvOps_tasks, before_index_ops, in_between_index_ops])
            self._run_after_index_tasks()
        except Exception, ex:
            raise

    def test_autofailover(self):
        autofailover_timeout = 30
        status = RestConnection(self.master).update_autofailover_settings(True, autofailover_timeout)
        self.assertTrue(status, 'failed to change autofailover_settings!')
        self._run_initial_index_tasks()
        servr_out = self.nodes_out_list
        remote = RemoteMachineShellConnection(servr_out[0])
        try:
            kvOps_tasks = self._run_kvops_tasks()
            before_index_ops = self._run_before_index_tasks()
            remote.stop_server()
            self.sleep(autofailover_timeout + 10, "Wait for autofailover")
            rebalance = self.cluster.async_rebalance(self.servers[:self.nodes_init],
                                   [], [servr_out[0]])
            in_between_index_ops = self._run_in_between_tasks()
            rebalance.result()
            self._run_tasks([kvOps_tasks, before_index_ops, in_between_index_ops])
            self._run_after_index_tasks()
        except Exception, ex:
            raise
        finally:
            remote.start_server()
            tasks = self.async_check_and_run_operations(buckets = self.buckets, after = True)
            for task in tasks:
                task.result()

    def test_network_partitioning(self):
        self._run_initial_index_tasks()
        try:
            kvOps_tasks = self._run_kvops_tasks()
            before_index_ops = self._run_before_index_tasks()
            for node in self.nodes_out_list:
                self.start_firewall_on_node(node)
            in_between_index_ops = self._run_in_between_tasks()
            self._run_tasks([kvOps_tasks, before_index_ops, in_between_index_ops])
            self._run_after_index_tasks()
        except Exception, ex:
            raise
        finally:
            for node in self.nodes_out_list:
                self.stop_firewall_on_node(node)
            self.sleep(1)

    def test_couchbase_bucket_compaction(self):
        self._run_initial_index_tasks()
        # Run Compaction Here
        # Run auto-compaction to remove the tomb stones
        compact_tasks = []
        kvOps_tasks = self._run_kvops_tasks()
        before_index_ops = self._run_before_index_tasks()
        for bucket in self.buckets:
            compact_tasks.append(self.cluster.async_compact_bucket(self.master,bucket))
        in_between_index_ops = self._run_in_between_tasks()
        self._run_tasks([kvOps_tasks, before_index_ops, in_between_index_ops])
        for task in compact_tasks:
            task.result()
        self._run_after_index_tasks()

    def test_warmup(self):
        self._run_initial_index_tasks()
        kvOps_tasks = self._run_kvops_tasks()
        before_index_ops = self._run_before_index_tasks()
        for server in self.nodes_out_list:
            remote = RemoteMachineShellConnection(server)
            remote.stop_server()
            remote.start_server()
            remote.disconnect()
        in_between_index_ops = self._run_in_between_tasks()
        ClusterOperationHelper.wait_for_ns_servers_or_assert(self.servers, self)
        self._run_tasks([kvOps_tasks, before_index_ops, in_between_index_ops])
        self._run_after_index_tasks()

    def test_couchbase_bucket_flush(self):
        self._run_initial_index_tasks()
        kvOps_tasks = self._run_kvops_tasks()
        before_index_ops = self._run_before_index_tasks()
        #Flush the bucket
        for bucket in self.buckets:
            RestConnection(self.master).flush_bucket(bucket.name)
        in_between_index_ops = self._run_in_between_tasks()
        self._run_tasks([kvOps_tasks, before_index_ops, in_between_index_ops])
        self._run_after_index_tasks()

    def _calculate_scan_vector(self):
        self.scan_vectors = None
        if self.scan_vectors != None:
            self.scan_vectors = self.gen_scan_vector(use_percentage = self.scan_vector_per_values,
             use_random = self.random_scan_vector)

    def _redefine_index_usage(self):
        qdfs = []
        if not self.use_replica :
            return
        if self.use_replica_when_active_down and \
            (self.ops_map["before"]["query_ops"] or self.ops_map["in_between"]["query_ops"])\
            and not self.all_index_nodes_lost:
            for query_definition in self.query_definitions:
                if query_definition.index_name in self.index_lost_during_move_out:
                    query_definition.index_name = query_definition.index_name+"_replica"
                qdfs.append(query_definition)
            self.query_definitions = qdfs
        elif self.ops_map["before"]["query_ops"] \
         or self.ops_map["in_between"]["query_ops"] \
         or self.all_index_nodes_lost:
            for query_definition in self.query_definitions:
                if query_definition.index_name in self.index_lost_during_move_out:
                    query_definition.index_name = "#primary"
                qdfs.append(query_definition)
            self.query_definitions = qdfs

    def _create_replica_index_when_indexer_is_down(self, index_lost_during_move_out):
        memory = []
        static_node_list = self._find_nodes_not_moved_out()
        tasks = []
        if self.use_replica_when_active_down and self.ops_map["before"]["query_ops"] or \
        self.use_replica_when_active_down and self.ops_map["in_between"]["query_ops"] or \
        self.use_replica_when_active_down and self.ops_map["after"]["query_ops"]:
            for query_definition in self.query_definitions:
                if query_definition.index_name in index_lost_during_move_out:
                    copy_of_query_definition = copy.deepcopy(query_definition)
                    copy_of_query_definition.index_name = query_definition.index_name+"_replica"
                    for node in static_node_list:
                        if copy_of_query_definition.index_name not in memory:
                            deploy_node_info = ["{0}:{1}".format(node.ip,node.port)]
                            for bucket in self.buckets:
                                self.create_index(
                                    bucket.name,
                                    copy_of_query_definition,
                                    deploy_node_info = deploy_node_info)
                            memory.append(copy_of_query_definition.index_name)

    def _find_nodes_not_moved_out(self):
        index_nodes = self.get_nodes_from_services_map(service_type = "index", get_all_nodes = True)
        index_nodes = copy.deepcopy(index_nodes)
        out_list = []
        list = []
        index_nodes_out = []
        for index_node in self.nodes_out_list:
            out_list.append("{0}:{1}".format(index_node.ip,index_node.port))
        for server in index_nodes:
            key = "{0}:{1}".format(server.ip,server.port)
            if key not in out_list:
                list.append(server)
            else:
                index_nodes_out.append(server)
        if len(index_nodes_out) == len(self.nodes_out_list):
            self.all_index_nodes_lost=True
        return list

    def _find_list_of_indexes_lost(self):
        index_node_count = 0
        memory =[]
        index_lost_during_move_out = []
        for query_definition in self.query_definitions:
            if index_node_count < len(self.index_nodes_out):
                if query_definition.index_name not in memory:
                    index_lost_during_move_out.append(query_definition.index_name)
                    memory.append(query_definition.index_name)
                    index_node_count+=1
        return index_lost_during_move_out

    def _run_initial_index_tasks(self):
        self.log.info("<<<<< START INITIALIZATION PHASE >>>>>>")
        self._calculate_scan_vector()
        tasks = self.async_check_and_run_operations(buckets = self.buckets, initial = True,
            scan_consistency = self.scan_consistency, scan_vectors = self.scan_vectors)
        self._run_tasks([tasks])
        self.log.info("<<<<< END INITIALIZATION PHASE >>>>>>")

    def _run_before_index_tasks(self):
        if self.ops_map["before"]["create_index"]:
            self.index_nodes_out = []
        self._redefine_index_usage()
        tasks = self.async_check_and_run_operations(buckets = self.buckets, before = True,
            scan_consistency = self.scan_consistency, scan_vectors = self.scan_vectors)
        return tasks

    def _run_in_between_tasks(self):
        tasks_ops = []
        if self.ops_map["in_between"]["create_index"]:
            self.index_nodes_out = []
        self._redefine_index_usage()
        tasks = self.async_check_and_run_operations(buckets = self.buckets, in_between = True,
            scan_consistency = self.scan_consistency, scan_vectors = self.scan_vectors)
        tasks += self._drop_indexes_in_between()
        return tasks

    def _drop_indexes_in_between(self):
        drop_tasks =[]
        if self.drop_indexes_in_between:
            drop_tasks = self.async_multi_drop_index(buckets = self.buckets,
             query_definitions = self.load_query_definitions)
        return drop_tasks

    def _run_kvops_tasks(self):
        tasks_ops =[]
        if self.doc_ops:
            tasks_ops = self.async_run_doc_ops()
        return tasks_ops

    def _run_after_index_tasks(self):
        tasks = self.async_check_and_run_operations(buckets = self.buckets, after = True,
            scan_consistency = self.scan_consistency, scan_vectors = self.scan_vectors)
        self._run_tasks([tasks])

    def _run_tasks(self, tasks_list):
        for tasks in tasks_list:
            for task in tasks:
                task.result()