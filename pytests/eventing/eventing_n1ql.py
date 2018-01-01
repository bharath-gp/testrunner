from lib.couchbase_helper.tuq_helper import N1QLHelper
from lib.membase.api.rest_client import RestConnection
from lib.testconstants import STANDARD_BUCKET_PORT
from pytests.eventing.eventing_base import EventingBaseTest, log
from pytests.eventing.eventing_constants import HANDLER_CODE, HANDLER_CODE_ERROR


class EventingN1QL(EventingBaseTest):
    def setUp(self):
        super(EventingN1QL, self).setUp()
        if self.create_functions_buckets:
            self.bucket_size = 100
            log.info(self.bucket_size)
            bucket_params = self._create_bucket_params(server=self.server, size=self.bucket_size,
                                                       replicas=self.num_replicas)
            self.cluster.create_standard_bucket(name=self.src_bucket_name, port=STANDARD_BUCKET_PORT + 1,
                                                bucket_params=bucket_params)
            self.src_bucket = RestConnection(self.master).get_buckets()
            self.cluster.create_standard_bucket(name=self.dst_bucket_name, port=STANDARD_BUCKET_PORT + 1,
                                                bucket_params=bucket_params)
            self.cluster.create_standard_bucket(name=self.metadata_bucket_name, port=STANDARD_BUCKET_PORT + 1,
                                                bucket_params=bucket_params)
            self.buckets = RestConnection(self.master).get_buckets()
        self.gens_load = self.generate_docs(self.docs_per_day)
        self.expiry = 3
        self.n1ql_node = self.get_nodes_from_services_map(service_type="n1ql")
        self.n1ql_helper = N1QLHelper(shell=self.shell,
                                      max_verify=self.max_verify,
                                      buckets=self.buckets,
                                      item_flag=self.item_flag,
                                      n1ql_port=self.n1ql_port,
                                      full_docs_list=self.full_docs_list,
                                      log=self.log, input=self.input,
                                      master=self.master,
                                      use_rest=True
                                      )

    def tearDown(self):
        super(EventingN1QL, self).tearDown()

    def test_delete_from_n1ql_from_update(self):
        self.load(self.gens_load, buckets=self.src_bucket, flag=self.item_flag, verify_data=False,
                  batch_size=self.batch_size)
        self.n1ql_helper.create_primary_index(using_gsi=True, server=self.n1ql_node)
        body = self.create_save_function_body(self.function_name, HANDLER_CODE.N1QL_DELETE_UPDATE, worker_count=3)
        self.deploy_function(body)
        # Wait for eventing to catch up with all the create mutations and verify results
        self.verify_eventing_results(self.function_name, self.docs_per_day * 2016, on_delete=True)
        self.undeploy_and_delete_function(body)
        query = "drop primary index on "+ self.src_bucket_name
        self.n1ql_helper.run_cbq_query(query=query,server=self.n1ql_node)

    def test_n1ql_prepare_statement(self):
        self.load(self.gens_load, buckets=self.src_bucket, flag=self.item_flag, verify_data=False,
                  batch_size=self.batch_size)
        self.n1ql_helper.create_primary_index(using_gsi=True, server=self.n1ql_node)
        query = "PREPARE test from DELETE from " + self.src_bucket_name + " where mutated=0"
        self.n1ql_helper.run_cbq_query(query=query, server=self.n1ql_node)
        body = self.create_save_function_body(self.function_name, HANDLER_CODE.N1QL_PREPARE, worker_count=3)
        self.deploy_function(body)
        # Wait for eventing to catch up with all the create mutations and verify results
        self.verify_eventing_results(self.function_name, self.docs_per_day * 2016, on_delete=True)
        self.undeploy_and_delete_function(body)
        query = "drop primary index on " + self.src_bucket_name
        self.n1ql_helper.run_cbq_query(query=query, server=self.n1ql_node)


    def test_n1ql_DML(self):
        self.load(self.gens_load, buckets=self.src_bucket, flag=self.item_flag, verify_data=False,
                  batch_size=self.batch_size)
        self.n1ql_helper.create_primary_index(using_gsi=True, server=self.n1ql_node)
        body = self.create_save_function_body(self.function_name,HANDLER_CODE.N1QL_DML,dcp_stream_boundary="from_now",execution_timeout=5)
        self.deploy_function(body)
        query = "UPDATE "+self.src_bucket_name+" set mutated=1 where mutated=0 limit 1"
        self.n1ql_helper.run_cbq_query(query=query, server=self.n1ql_node)
        self.verify_eventing_results(self.function_name, 6, skip_stats_validation=True)
        self.undeploy_and_delete_function(body)

    def test_n1ql_DDL(self):
        self.load(self.gens_load, buckets=self.src_bucket, flag=self.item_flag, verify_data=False,
                  batch_size=self.batch_size)
        body = self.create_save_function_body(self.function_name,HANDLER_CODE.N1QL_DDL,dcp_stream_boundary="from_now")
        self.deploy_function(body)
        #create a mutation via N1QL
        self.n1ql_helper.create_primary_index(using_gsi=True, server=self.n1ql_node)
        query = "UPDATE "+self.src_bucket_name+" set mutated=1 where mutated=0 limit 1"
        self.n1ql_helper.run_cbq_query(query=query, server=self.n1ql_node)
        #verify deployment should fail
        self.verify_eventing_results(self.function_name, 3, skip_stats_validation=True)
        self.undeploy_and_delete_function(body)

    def test_recursive_mutation_n1ql(self):
        self.load(self.gens_load, buckets=self.src_bucket, flag=self.item_flag, verify_data=False,
                  batch_size=self.batch_size)
        body = self.create_save_function_body(self.function_name, HANDLER_CODE.RECURSIVE_MUTATION, dcp_stream_boundary="from_now")
        self.deploy_function(body)
        # create a mutation via N1QL
        self.n1ql_helper.create_primary_index(using_gsi=True, server=self.n1ql_node)
        query = "UPDATE " + self.src_bucket_name + " set mutated=1 where mutated=0 limit 1"
        self.n1ql_helper.run_cbq_query(query=query, server=self.n1ql_node)
        # verify deployment should fail
        self.verify_eventing_results(self.function_name, 0)
        self.undeploy_and_delete_function(body)

    def test_grant_revoke(self):
        self.load(self.gens_load, buckets=self.src_bucket, flag=self.item_flag, verify_data=False,
                  batch_size=self.batch_size)
        body = self.create_save_function_body(self.function_name,HANDLER_CODE.GRANT_REVOKE,dcp_stream_boundary="from_now")
        self.deploy_function(body)
        #create a mutation via N1QL
        self.n1ql_helper.create_primary_index(using_gsi=True, server=self.n1ql_node)
        query = "UPDATE "+self.src_bucket_name+" set mutated=1 where mutated=0 limit 1"
        self.n1ql_helper.run_cbq_query(query=query, server=self.n1ql_node)
        #verify deployment should fail
        self.verify_eventing_results(self.function_name, 2, skip_stats_validation=True)
        self.verify_user_noroles("cbadminbucket")
        self.undeploy_and_delete_function(body)

    def test_n1ql_curl(self):
        self.load(self.gens_load, buckets=self.src_bucket, flag=self.item_flag, verify_data=False,
                  batch_size=self.batch_size)
        body = self.create_save_function_body(self.function_name,HANDLER_CODE.CURL,dcp_stream_boundary="from_now")
        self.deploy_function(body)
        #create a mutation via N1QL
        self.n1ql_helper.create_primary_index(using_gsi=True, server=self.n1ql_node)
        query = "UPDATE "+self.src_bucket_name+" set mutated=1 where mutated=0 limit 1"
        self.n1ql_helper.run_cbq_query(query=query, server=self.n1ql_node)
        self.verify_eventing_results(self.function_name, 1, skip_stats_validation=True)
        self.undeploy_and_delete_function(body)


    def test_anonymous(self):
        self.load(self.gens_load, buckets=self.src_bucket, flag=self.item_flag, verify_data=False,
                  batch_size=self.batch_size)
        body = self.create_save_function_body(self.function_name,HANDLER_CODE.ANONYMOUS,dcp_stream_boundary="from_now")
        self.deploy_function(body)
        #create a mutation via N1QL
        self.n1ql_helper.create_primary_index(using_gsi=True, server=self.n1ql_node)
        query = "UPDATE "+self.src_bucket_name+" set mutated=1 where mutated=0 limit 1"
        self.n1ql_helper.run_cbq_query(query=query, server=self.n1ql_node)
        #verify that n1ql query will fail
        self.verify_eventing_results(self.function_name, 2, skip_stats_validation=True)
        self.undeploy_and_delete_function(body)

    def test_recursion_function(self):
        self.load(self.gens_load, buckets=self.src_bucket, flag=self.item_flag, verify_data=False,
                  batch_size=self.batch_size)
        body = self.create_save_function_body(self.function_name, HANDLER_CODE.RECURSION_FUNCTION,
                                              dcp_stream_boundary="from_now",execution_timeout=5)
        self.deploy_function(body)
        # create a mutation via N1QL
        self.n1ql_helper.create_primary_index(using_gsi=True, server=self.n1ql_node)
        query = "UPDATE " + self.src_bucket_name + " set mutated=1 where mutated=0 limit 1"
        self.n1ql_helper.run_cbq_query(query=query, server=self.n1ql_node)
        # verify that n1ql query will fail
        self.verify_eventing_results(self.function_name, 2, skip_stats_validation=True)
        self.undeploy_and_delete_function(body)

    def test_global_variable(self):
        self.load(self.gens_load, buckets=self.src_bucket, flag=self.item_flag, verify_data=False,
                  batch_size=self.batch_size)
        body = self.create_save_function_body(self.function_name, HANDLER_CODE_ERROR.GLOBAL_VARIABLE,
                                              dcp_stream_boundary="from_now")
        try :
            self.deploy_function(body,deployment_fail=True)
        except Exception as e:
            if "Only function declaration are allowed in global scope" not in str(e):
                self.fail("Deployment is expected to be failed but no message of failure")



    def test_empty_handler(self):
        self.load(self.gens_load, buckets=self.src_bucket, flag=self.item_flag, verify_data=False,
                  batch_size=self.batch_size)
        body = self.create_save_function_body(self.function_name, HANDLER_CODE_ERROR.EMPTY,
                                              dcp_stream_boundary="from_now")
        self.deploy_function(body,deployment_fail=True)
        # TODO : more assertion needs to be validate after MB-27126

    def test_without_update_delete(self):
        self.load(self.gens_load, buckets=self.src_bucket, flag=self.item_flag, verify_data=False,
                  batch_size=self.batch_size)
        body = self.create_save_function_body(self.function_name, HANDLER_CODE_ERROR.RANDOM,
                                              dcp_stream_boundary="from_now")
        self.deploy_function(body, deployment_fail=True)
        # TODO : more assertion needs to be validate after MB-27126

    def test_anonymous_with_cron_timer(self):
        self.load(self.gens_load, buckets=self.src_bucket, flag=self.item_flag, verify_data=False,
                  batch_size=self.batch_size)
        body = self.create_save_function_body(self.function_name, HANDLER_CODE_ERROR.ANONYMOUS_CRON_TIMER,
                                              dcp_stream_boundary="from_now")
        self.deploy_function(body, deployment_fail=True)
        # TODO : more assertion needs to be validate after MB-27155

    def test_anonymous_with_doc_timer(self):
        self.load(self.gens_load, buckets=self.src_bucket, flag=self.item_flag, verify_data=False,
                  batch_size=self.batch_size)
        body = self.create_save_function_body(self.function_name, HANDLER_CODE_ERROR.ANONYMOUS_DOC_TIMER,
                                              dcp_stream_boundary="from_now")
        self.deploy_function(body, deployment_fail=True)
        # TODO : more assertion needs to be validate after MB-27155