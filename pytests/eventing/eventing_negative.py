import logging

from lib.membase.api.rest_client import RestConnection
from lib.testconstants import STANDARD_BUCKET_PORT
from pytests.eventing.eventing_base import EventingBaseTest
from pytests.eventing.eventing_constants import HANDLER_CODE

log = logging.getLogger()


class EventingNegative(EventingBaseTest):
    def setUp(self):
        super(EventingNegative, self).setUp()
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

    def tearDown(self):
        super(EventingNegative, self).tearDown()

    def test_delete_function_when_function_is_in_deployed_state_and_which_is_already_deleted(self):
        self.load(self.gens_load, buckets=self.src_bucket, flag=self.item_flag, verify_data=False,
                  batch_size=self.batch_size)
        body = self.create_save_function_body(self.function_name, HANDLER_CODE.BUCKET_OPS_ON_UPDATE, worker_count=3)
        self.deploy_function(body)
        # Wait for eventing to catch up with all the create mutations and verify results
        self.verify_eventing_results(self.function_name, self.docs_per_day * 2016)
        # Try deleting a function which is still in deployed state
        try:
            self.delete_function(body)
        except Exception as ex:
            log.info("output from delete API before undeploying function: {0}".format(str(ex)))
            message = "Skipping delete request from temp store for app: {0} as it hasn't been undeployed".format(
                self.function_name)
            if message not in str(ex):
                self.fail("Function delete succeeded even when function was in deployed state")
        self.undeploy_and_delete_function(body)
        try:
            # Try deleting a function which is already deleted
            self.delete_function(body)
        except Exception as ex:
            message = "App: {0} not deployed".format(self.function_name)
            if message not in str(ex):
                self.fail("Function delete succeeded even when function was in deployed state")

    def test_deploy_function_where_source_metadata_and_destination_buckets_dont_exist(self):
        # delete source, metadata and destination buckets
        for bucket in self.buckets:
            self.rest.delete_bucket(bucket.name)
        body = self.create_save_function_body(self.function_name, HANDLER_CODE.BUCKET_OPS_ON_UPDATE, worker_count=3)
        try:
            self.rest.save_function(body['appname'], body)
            self.rest.deploy_function(body['appname'], body)
        except Exception as ex:
            if "Source bucket missing" not in str(ex):
                self.fail("Function save/deploy succeeded even when src/dst/metadata buckets doesn't exist")

    def test_deploy_function_where_source_and_metadata_buckets_are_same(self):
        self.load(self.gens_load, buckets=self.src_bucket, flag=self.item_flag, verify_data=False,
                  batch_size=self.batch_size)
        body = self.create_save_function_body(self.function_name, HANDLER_CODE.BUCKET_OPS_ON_UPDATE, worker_count=3)
        # set both src and metadata bucket as same
        body['depcfg']['metadata_bucket'] = self.src_bucket_name
        try:
            self.rest.save_function(body['appname'], body)
            # Try to deploy the function
            self.rest.deploy_function(body['appname'], body)
        except Exception as ex:
            if "Source bucket same as metadata bucket" not in str(ex):
                self.fail("Eventing function allowed both source and metadata bucket to be same")

    def test_eventing_with_memcached_buckets(self):
        # delete existing couchbase buckets which will be created as part of setup
        for bucket in self.buckets:
            self.rest.delete_bucket(bucket.name)
        # create memcached bucket with the same name
        bucket_params = self._create_bucket_params(server=self.server, size=self.bucket_size,
                                                   replicas=self.num_replicas)
        tasks = []
        for bucket in self.buckets:
            tasks.append(self.cluster.async_create_memcached_bucket(name=bucket.name,
                                                                    port=STANDARD_BUCKET_PORT + 1,
                                                                    bucket_params=bucket_params))
        for task in tasks:
            task.result()
        body = self.create_save_function_body(self.function_name, HANDLER_CODE.BUCKET_OPS_ON_UPDATE, worker_count=3)
        try:
            self.rest.save_function(body['appname'], body)
            self.rest.deploy_function(body['appname'], body)
        except Exception as ex:
            if "Source bucket is memcached, should be either couchbase or ephemeral" not in str(ex):
                self.fail("Eventing function allowed both source and metadata bucket to be memcached buckets")

    def test_src_metadata_and_dst_bucket_flush_and_delete_when_eventing_is_processing_mutations(self):
        body = self.create_save_function_body(self.function_name, HANDLER_CODE.BUCKET_OPS_WITH_DOC_TIMER)
        self.deploy_function(body)
        self.load(self.gens_load, buckets=self.src_bucket, flag=self.item_flag, verify_data=False,
                  batch_size=self.batch_size)
        # flush source, metadata and destination buckets when eventing is processing_mutations
        for bucket in self.buckets:
            self.rest.flush_bucket(bucket.name)
        # delete source, metadata and destination buckets when eventing is processing_mutations
        for bucket in self.buckets:
                self.rest.delete_bucket(bucket.name)
        self.undeploy_and_delete_function(body)
        # check if all the eventing-consumers are cleaned up
        # Validation of any issues like panic will be taken care by teardown method
        self.assertTrue(self.check_if_eventing_consumers_are_cleaned_up(),
                        msg="eventing-consumer processes are not cleaned up even after undeploying the function")

    def test_undeploy_when_function_is_still_in_bootstrap_state(self):
        self.load(self.gens_load, buckets=self.src_bucket, flag=self.item_flag, verify_data=False,
                  batch_size=self.batch_size)
        body = self.create_save_function_body(self.function_name, HANDLER_CODE.BUCKET_OPS_ON_UPDATE, worker_count=3)
        self.deploy_function(body, wait_for_bootstrap=False)
        try:
            # Try undeploying the function when it is still bootstrapping
            self.undeploy_function(body)
        except Exception as ex:
            if "not bootstrapped, discarding request to undeploy it" not in str(ex):
                self.fail("Function undeploy succeeded even when function was in bootstrapping state")
        # Wait for eventing to catch up with all the create mutations and verify results
        self.wait_for_bootstrap_to_complete(body['appname'])
        self.verify_eventing_results(self.function_name, self.docs_per_day * 2016)
        self.undeploy_and_delete_function(body)
