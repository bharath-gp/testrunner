"""collections_index_basics.py: This test file contains tests for basic index operation in Collections context

__author__ = "Hemant Rajput"
__maintainer = "Hemant Rajput"
__email__ = "Hemant.Rajput@couchbase.com"
__git_user__ = "hrajput89"
__created_on__ = "26/05/20 2:13 pm" 

"""
import random

from couchbase_helper.documentgenerator import SDKDataLoader
from couchbase_helper.query_definitions import QueryDefinition
from .base_gsi import BaseSecondaryIndexingTests
from collection.collections_rest_client import CollectionsRest
from collection.collections_stats import CollectionsStats
from tasks import task


class CollectionsIndexBasics(BaseSecondaryIndexingTests):
    def setUp(self):
        super(CollectionsIndexBasics, self).setUp()
        self.log.info("==============  CollectionsIndexBasics setup has started ==============")
        self.rest.delete_all_buckets()
        self.num_scopes = self.input.param("num_scopes", 1)
        self.num_collections = self.input.param("num_collections", 1)
        self.test_bucket = self.input.param('test_bucket', 'test_bucket')
        self.bucket_params = self._create_bucket_params(server=self.master, size=100,
                                                        replicas=self.num_replicas, bucket_type=self.bucket_type,
                                                        enable_replica_index=self.enable_replica_index,
                                                        eviction_policy=self.eviction_policy, lww=self.lww)
        self.cluster.create_standard_bucket(name=self.test_bucket, port=11222,
                                            bucket_params=self.bucket_params)
        self.buckets = self.rest.get_buckets()
        self.cli_rest = CollectionsRest(self.master)
        self.stat = CollectionsStats(self.master)
        self.scope_prefix = 'test_scope'
        self.collection_prefix = 'test_collection'
        self.run_cbq_query = self.n1ql_helper.run_cbq_query
        self.num_of_docs_per_collection = 1000
        self.log.info("==============  CollectionsIndexBasics setup has completed ==============")

    def tearDown(self):
        self.log.info("==============  CollectionsIndexBasics tearDown has started ==============")
        super(CollectionsIndexBasics, self).tearDown()
        self.log.info("==============  CollectionsIndexBasics tearDown has completed ==============")

    def suite_tearDown(self):
        pass

    def suite_setUp(self):
        pass

    def _prepare_collection_for_indexing(self, num_scopes=1, num_collections=1, num_of_docs_per_collection=1000,
                                         skip_defaults=True, indexes_before_load=False, json_template="Person"):
        self.namespace = []
        pre_load_idx_pri = None
        pre_load_idx_gsi = None
        self.cli_rest.create_scope_collection_count(scope_num=num_scopes, collection_num=num_collections,
                                                    scope_prefix=self.scope_prefix,
                                                    collection_prefix=self.collection_prefix,
                                                    bucket=self.test_bucket)
        self.scopes = self.cli_rest.get_bucket_scopes(bucket=self.test_bucket)
        self.collections = self.cli_rest.get_bucket_collections(bucket=self.test_bucket)

        if skip_defaults:
            self.scopes.remove('_default')
            self.collections.remove('_default')
        if num_of_docs_per_collection > 0:
            for s_item in self.scopes:
                for c_item in self.collections:
                    self.namespace.append(f'default:{self.test_bucket}.{s_item}.{c_item}')
                    if indexes_before_load:
                        pre_load_idx_pri = QueryDefinition(index_name='pre_load_idx_pri')
                        pre_load_idx_gsi = QueryDefinition(index_name='pre_load_idx_gsi', index_fields=['firstname'])
                        query = pre_load_idx_pri.generate_primary_index_create_query(namespace=self.namespace[0])
                        self.run_cbq_query(query=query)
                        query = pre_load_idx_gsi.generate_index_create_query(namespace=self.namespace[0])
                        self.run_cbq_query(query=query)
                    self.gen_create = SDKDataLoader(num_ops=num_of_docs_per_collection, percent_create=100,
                                                    percent_update=0, percent_delete=0, scope=s_item,
                                                    collection=c_item, json_template=json_template)
                    self._load_all_buckets(self.master, self.gen_create)
                    # gens_load = self.generate_docs(self.docs_per_day)
                    # self.load(gens_load, flag=self.item_flag, verify_data=False, batch_size=self.batch_size,
                    # collection=f"{s_item}.{c_item}")

        return pre_load_idx_pri, pre_load_idx_gsi

    def test_create_primary_index_for_collections(self):
        self._prepare_collection_for_indexing()
        collection_namespace = self.namespace[0]
        query_gen_1 = QueryDefinition(index_name='`#primary`')
        query_gen_2 = QueryDefinition(index_name='name_primary_idx')
        # preparing index
        try:
            query = query_gen_1.generate_primary_index_create_query(namespace=collection_namespace,
                                                                    deploy_node_info=self.deploy_node_info,
                                                                    defer_build=self.defer_build,
                                                                    num_replica=self.num_index_replicas)

            self.run_cbq_query(query=query)
            if self.defer_build:
                query = query_gen_1.generate_build_query(collection_namespace)
                self.run_cbq_query(query=query)
            self.wait_until_indexes_online(defer_build=self.defer_build)
            query = f'SELECT COUNT(*) from {collection_namespace}'
            count = self.run_query_with_retry(query=query, expected_result=self.num_of_docs_per_collection,
                                              is_count_query=True)
            self.assertEqual(count, self.num_of_docs_per_collection, "Docs count not matching")
            # stat = self.stat.get_collection_stats(bucket=self.buckets[0])

            # Checking for named primary index
            query = query_gen_2.generate_primary_index_create_query(namespace=collection_namespace,
                                                                    deploy_node_info=self.deploy_node_info,
                                                                    defer_build=self.defer_build,
                                                                    num_replica=self.num_index_replicas)
            self.run_cbq_query(query=query)
            if self.defer_build:
                query = query_gen_2.generate_build_query(collection_namespace)
                self.run_cbq_query(query=query)
            self.wait_until_indexes_online(defer_build=self.defer_build)
            query = f'SELECT COUNT(*) from {collection_namespace}'
            count = self.run_query_with_retry(query=query, expected_result=self.num_of_docs_per_collection,
                                              is_count_query=True)
            self.assertEqual(count, self.num_of_docs_per_collection, "Docs count not matching")
        except Exception as err:
            self.fail(str(err))
        finally:
            query_1 = query_gen_1.generate_index_drop_query(namespace=collection_namespace)
            query_2 = query_gen_2.generate_index_drop_query(namespace=collection_namespace)
            self.run_cbq_query(query=query_1)
            self.run_cbq_query(query=query_2)

    def test_gsi_for_collection(self):
        pre_load_idx_pri, pre_load_idx_gsi = self._prepare_collection_for_indexing(indexes_before_load=True)
        collection_namespace = self.namespace[0]

        query_gen = QueryDefinition(index_name='idx', index_fields=['age'])
        indx_gen = QueryDefinition(index_name='meta_idx', index_fields=['meta().expiration'])
        primary_gen = QueryDefinition(index_name='`#primary`')
        try:
            # Checking for secondary index creation on named collection
            query = query_gen.generate_index_create_query(namespace=collection_namespace, defer_build=self.defer_build)
            self.run_cbq_query(query=query)
            if self.defer_build:
                query = query_gen.generate_build_query(collection_namespace)
                self.run_cbq_query(query=query)
            self.wait_until_indexes_online(defer_build=self.defer_build)
            # todo (why it's failing even though build is complete)
            self.sleep(5)

            query = indx_gen.generate_index_create_query(namespace=collection_namespace, defer_build=self.defer_build)
            self.run_cbq_query(query=query)
            if self.defer_build:
                query = indx_gen.generate_build_query(collection_namespace)
                self.run_cbq_query(query=query)
            self.wait_until_indexes_online(defer_build=self.defer_build)
            # todo (why it's failing even though build is complete)
            self.sleep(5)

            query = primary_gen.generate_primary_index_create_query(namespace=collection_namespace,
                                                                    deploy_node_info=self.deploy_node_info,
                                                                    defer_build=self.defer_build,
                                                                    num_replica=self.num_index_replicas)
            self.run_cbq_query(query=query)
            if self.defer_build:
                query = primary_gen.generate_build_query(collection_namespace)
                self.run_cbq_query(query=query)
            self.wait_until_indexes_online(defer_build=self.defer_build)
            # todo (why it's failing even though build is complete)
            self.sleep(5)

            query = f'SELECT age from {collection_namespace} where age > 65'
            result = self.run_cbq_query(query=query)['results']
            self.assertNotEqual(len(result), 0, f'Actual : {result}')

            # creating few docs to check the index behavior for insert with expiration
            doc_count_query = f'SELECT count(*) FROM {collection_namespace}'
            count = self.run_cbq_query(query=doc_count_query)['results'][0]['$1']

            value = {
                "city": "Test Dee",
                "country": "Test Verde",
                "firstName": "Test name",
                "lastName": "Test Funk",
                "streetAddress": "66877 Williamson Terrace",
                "suffix": "V",
                "title": "International Solutions Coordinator"
            }
            # exptime = 20
            exptime = 0
            for key_id in range(20):
                doc_id = f'new_doc_{key_id}'
                doc_body = value
                doc_body['age'] = random.randint(30, 70)
                insert_query = f"INSERT into {collection_namespace} (KEY, VALUE) VALUES('{doc_id}', {doc_body}," \
                               f" {{'expiration': {exptime}}}) "
                self.run_cbq_query(query=insert_query)

            count += 20
            doc_count = self.run_query_with_retry(query=doc_count_query, expected_result=count, is_count_query=True)
            self.assertEqual(doc_count, count,
                             f"Results are not matching. Actual: {result}, Expected: {count} ")

            # # Checking for TTL
            # self.sleep(20, 'Waiting for docs to get expired')
            # count -= 20
            # query = f'SELECT meta().id FROM {collection_namespace} WHERE meta().expiration IS NOT NULL'
            # result = self.run_cbq_query(query=query)['results']
            # self.assertEqual(len(result), count, f"Results are not matching. Actual: {result}, Expected: {count} ")

            # deleting docs
            query = f'SELECT meta().id FROM {collection_namespace}'
            doc_ids = self.run_cbq_query(query=query)['results']
            docs_to_delete = [doc_id['id'] for doc_id in random.choices(doc_ids, k=10)]
            doc_ids = ", ".join([f'"{item}"' for item in docs_to_delete])
            delete_query = f'DELETE FROM {collection_namespace} d WHERE meta(d).id in [{doc_ids}] RETURNING d'
            self.run_cbq_query(query=delete_query)
            count -= len(docs_to_delete)
            doc_count = self.run_query_with_retry(query=doc_count_query, expected_result=count, is_count_query=True)
            self.assertEqual(doc_count, count, f"Actual: {doc_count}, Expected: {count}")

            # updating docs
            query = f'UPDATE {collection_namespace} SET updated = true WHERE age > 65'
            self.run_cbq_query(query=query)
            query = f'SELECT meta().id FROM {collection_namespace} WHERE age > 65'
            queried_docs = self.run_cbq_query(query=query)['results']
            queried_docs = sorted([item['id'] for item in queried_docs])
            query = f'SELECT meta().id FROM {collection_namespace} WHERE updated = true'
            updated_docs_ids = self.run_cbq_query(query=query)['results']
            updated_docs_ids = sorted([item['id'] for item in updated_docs_ids])

            self.assertEqual(queried_docs, updated_docs_ids, f"Actual: {queried_docs}, Expected: {updated_docs_ids}")
            doc_count = self.run_query_with_retry(query=doc_count_query, expected_result=count, is_count_query=True)
            self.assertEqual(doc_count, count, f"Actual: {doc_count}, Expected: {count}")

            # upserting docs
            upsert_doc_list = ['upsert-1', 'upsert-2']
            query = f'UPSERT INTO {collection_namespace} (KEY, VALUE) VALUES ' \
                    f'("upsert-1", {{ "firstName": "Michael", "age": 72}}),' \
                    f'("upsert-2", {{"firstName": "George", "age": 75}})' \
                    f' RETURNING VALUE name'
            self.run_cbq_query(query=query)
            self.sleep(5, 'Giving some time to indexer to index newly inserted docs')
            query = f'SELECT meta().id FROM {collection_namespace} WHERE age > 70'
            upsert_doc_ids = self.run_cbq_query(query=query)['results']
            upsert_doc_ids = sorted([item['id'] for item in upsert_doc_ids])
            self.assertEqual(upsert_doc_ids, upsert_doc_list,
                             f"Actual: {upsert_doc_ids}, Expected: {upsert_doc_list}")
            count += len(upsert_doc_list)
            doc_count = self.run_query_with_retry(query=doc_count_query, expected_result=count, is_count_query=True)
            self.assertEqual(doc_count, count, f"Actual: {doc_count}, Expected: {count}")

            # checking if pre-load indexes indexed docs
            query = f'SELECT COUNT(*) FROM {collection_namespace} WHERE firstName is not null'
            result = self.run_query_with_retry(query=query, expected_result=count, is_count_query=True)
            self.assertEqual(result, count, f"Actual: {doc_count}, Expected: {count}")

            query = f'SELECT COUNT(*) FROM {collection_namespace}'
            result = self.run_query_with_retry(query=query, expected_result=count, is_count_query=True)
            self.assertEqual(result, count, f"Actual: {doc_count}, Expected: {count}")
        except Exception as err:
            self.fail(str(err))
        finally:
            query = query_gen.generate_index_drop_query(namespace=collection_namespace)
            self.run_cbq_query(query=query)
            query = indx_gen.generate_index_drop_query(namespace=collection_namespace)
            self.run_cbq_query(query=query)
            query = primary_gen.generate_index_drop_query(namespace=collection_namespace)
            self.run_cbq_query(query=query)

            # Deleting pre-load-indexes
            query = pre_load_idx_pri.generate_index_drop_query(namespace=collection_namespace)
            self.run_cbq_query(query=query)
            query = pre_load_idx_gsi.generate_index_drop_query(namespace=collection_namespace)
            self.run_cbq_query(query=query)

    def test_multiple_indexes_on_same_field(self):
        self._prepare_collection_for_indexing()
        collection_namespace = self.namespace[0]
        primary_gen = QueryDefinition(index_name='`#primary`')
        query_gen = QueryDefinition(index_name='idx', index_fields=['age'])
        query_gen_copy = QueryDefinition(index_name='idx_copy', index_fields=['age'])
        # preparing index
        try:
            query = primary_gen.generate_primary_index_create_query(namespace=collection_namespace,
                                                                    deploy_node_info=self.deploy_node_info,
                                                                    defer_build=self.defer_build,
                                                                    num_replica=self.num_index_replicas)

            self.run_cbq_query(query=query)
            if self.defer_build:
                query = primary_gen.generate_build_query(collection_namespace)
                self.run_cbq_query(query=query)
            self.wait_until_indexes_online(defer_build=self.defer_build)
            query = f'SELECT COUNT(*) from {collection_namespace}'
            count = self.run_query_with_retry(query=query, expected_result=self.num_of_docs_per_collection,
                                              is_count_query=True)['results'][0]['$1']
            self.assertEqual(count, self.num_of_docs_per_collection, "Docs count not matching")

            query = query_gen.generate_index_create_query(namespace=collection_namespace, defer_build=self.defer_build)
            self.run_cbq_query(query=query)
            if self.defer_build:
                query = query_gen.generate_build_query(collection_namespace)
                self.run_cbq_query(query=query)
            self.wait_until_indexes_online(defer_build=self.defer_build)

            query = query_gen_copy.generate_index_create_query(namespace=collection_namespace,
                                                               defer_build=self.defer_build)
            self.run_cbq_query(query=query)
            if self.defer_build:
                query = query_gen_copy.generate_build_query(collection_namespace)
                self.run_cbq_query(query=query)
                self.wait_until_indexes_online(defer_build=self.defer_build)

            # Running query against GSI index idx and idx_copy
            query = f'select count(*) from {collection_namespace} where age is not null;'
            result = self.run_query_with_retry(query=query, expected_result=count, is_count_query=True)
            self.assertEqual(result, count, f"Actual: {result}, Expected: {count}")

        except Exception as err:
            self.fail(str(err))
        finally:
            query_1 = primary_gen.generate_index_drop_query(namespace=collection_namespace)
            query_2 = query_gen.generate_index_drop_query(namespace=collection_namespace)
            query_3 = query_gen_copy.generate_index_drop_query(namespace=collection_namespace)
            self.run_cbq_query(query=query_1)
            self.run_cbq_query(query=query_2)
            self.run_cbq_query(query=query_3)

    def test_gsi_indexes_with_WITH_clause(self):
        index_nodes = self.get_nodes_from_services_map(service_type="index",
                                                       get_all_nodes=True)
        if len(index_nodes) < 2:
            self.fail("Need at least 2 index nodes to run this test")
        self._prepare_collection_for_indexing()
        collection_namespace = self.namespace[0]

        # index creation with num replica
        index_gen = QueryDefinition(index_name='idx', index_fields=['age'])
        try:
            query = index_gen.generate_index_create_query(namespace=collection_namespace, defer_build=self.defer_build,
                                                          num_replica=1)
            self.run_cbq_query(query=query)
            if self.defer_build:
                query = index_gen.generate_build_query(collection_namespace)
                self.run_cbq_query(query=query)
            self.wait_until_indexes_online(defer_build=self.defer_build)

            # querying docs for the idx index
            query = f'SELECT COUNT(*) FROM {collection_namespace} WHERE age > 65'
            result = self.run_cbq_query(query=query)['results'][0]['$1']
            self.assertNotEqual(result, 0, f"Actual: {result}, Expected: 0")
        except Exception as err:
            self.fail(str(err))
        finally:
            query = index_gen.generate_index_drop_query(namespace=collection_namespace)
            self.run_cbq_query(query=query)

        # index creation with node info
        try:
            replica_nodes = []
            for node in index_nodes:
                replica_nodes.append(f'{node.ip}:8091')
            query = index_gen.generate_index_create_query(namespace=collection_namespace,
                                                          deploy_node_info=replica_nodes, defer_build=self.defer_build)
            self.run_cbq_query(query=query)
            if self.defer_build:
                query = index_gen.generate_build_query(collection_namespace)
                self.run_cbq_query(query=query)
            self.wait_until_indexes_online(defer_build=self.defer_build)

            # querying docs for the idx index
            query = f'SELECT COUNT(*) FROM {collection_namespace} WHERE age > 65'
            result = self.run_cbq_query(query=query)['results'][0]['$1']
            self.assertNotEqual(result, 0, f"Actual: {result}, Expected: 0")
        except Exception as err:
            self.fail(str(err))
        finally:
            query = index_gen.generate_index_drop_query(namespace=collection_namespace)
            self.run_cbq_query(query=query)

    def test_gsi_array_indexes(self):
        self._prepare_collection_for_indexing(json_template="Employee")
        collection_namespace = self.namespace[0]
        primary_gen = QueryDefinition(index_name='`#primary`')
        doc_count = self.run_cbq_query(query=f'select count(*) from {collection_namespace}')['results'][0]['$1']
        arr_index = "arr_index"
        # preparing index
        try:
            query = primary_gen.generate_primary_index_create_query(namespace=collection_namespace,
                                                                    deploy_node_info=self.deploy_node_info,
                                                                    defer_build=self.defer_build,
                                                                    num_replica=self.num_index_replicas)

            self.run_cbq_query(query=query)
            if self.defer_build:
                query = primary_gen.generate_build_query(collection_namespace)
                self.run_cbq_query(query=query)
            self.wait_until_indexes_online(defer_build=self.defer_build)

            # Creating Array index
            query = f"create index {arr_index} on {collection_namespace}(ALL ARRAY v.name for v in VMs END) "
            self.run_cbq_query(query=query)
            self.wait_until_indexes_online()
            # Run a query that uses array indexes
            query = f'select count(*) from {collection_namespace}  where any v in VMs satisfies v.name like "vm_%" END'
            result = self.run_cbq_query(query=query)['results'][0]['$1']
            self.assertEqual(result, doc_count, f"Expected: {doc_count}, Actual: {result}")
            # Dropping the indexer
            query = f"DROP INDEX {arr_index} ON {collection_namespace}"
            self.run_cbq_query(query=query)

            # Partial Indexes
            query = f"create index {arr_index} on {collection_namespace}(ALL ARRAY v.name for v in VMs END) " \
                    f"where join_mo > 8"
            self.run_cbq_query(query=query)
            self.wait_until_indexes_online()
            # Run a query that uses array indexes
            query = f'explain select count(*) from {collection_namespace}  where join_mo > 8 AND ' \
                    f'any v in VMs satisfies v.name like "vm_%" END'
            result = self.run_cbq_query(query=query)['results']
            self.assertEqual(result[0]['plan']['~children'][0]['scan']['index'], 'arr_index',
                             "Array index arr_index is not used.")
            query = f'explain select count(*) from {collection_namespace}  where join_mo > 7 AND ' \
                    f'any v in VMs satisfies v.name like "vm_%" END'
            result = self.run_cbq_query(query=query)['results']
            self.assertEqual(result[0]['plan']['~children'][0]['index'], '#primary',
                             "Array index arr_index is used.")
            # Dropping the indexer
            query = f"DROP INDEX {arr_index} ON {collection_namespace}"
            self.run_cbq_query(query=query)

            # Checking for Simplified index
            query = f"create index {arr_index} on {collection_namespace}(ALL  VMs)"
            self.run_cbq_query(query=query)
            self.wait_until_indexes_online()
            # Run a query that uses array indexes
            query = f' select count(*) from {collection_namespace} where ' \
                    f'any v in VMs satisfies v.name like "vm_%" and v.memory like "%1%" END'
            result = self.run_cbq_query(query=query)['results'][0]['$1']
            self.assertNotEqual(result, 1000)
            query = f'explain {query}'
            result = self.run_cbq_query(query=query)['results']
            self.assertEqual(result[0]['plan']['~children'][0]['scan']['index'], 'arr_index',
                             "Array index arr_index is not used.")
            # Dropping the indexer
            query = f"DROP INDEX {arr_index} ON {collection_namespace}"
            self.run_cbq_query(query=query)
        except Exception as err:
            # Dropping the indexer
            query = f"DROP INDEX {arr_index} ON {collection_namespace}"
            self.run_cbq_query(query=query)
            self.fail(str(err))
        finally:
            query = primary_gen.generate_index_drop_query(namespace=collection_namespace)
            self.run_cbq_query(query=query)

    def test_index_partitioning(self):
        self._prepare_collection_for_indexing(json_template="Employee")
        collection_namespace = self.namespace[0]
        arr_index = "arr_index"
        primary_gen = QueryDefinition(index_name='`#primary`')
        index_gen = QueryDefinition(index_name=arr_index, index_fields=['join_mo', 'join_day'],
                                    partition_by_fields=['meta().id'])
        try:
            query = primary_gen.generate_primary_index_create_query(namespace=collection_namespace,
                                                                    deploy_node_info=self.deploy_node_info,
                                                                    defer_build=self.defer_build,
                                                                    num_replica=self.num_index_replicas)

            self.run_cbq_query(query=query)
            if self.defer_build:
                query = primary_gen.generate_build_query(collection_namespace)
                self.run_cbq_query(query=query)
            self.wait_until_indexes_online(defer_build=self.defer_build)

            # Creating Paritioned index
            query = index_gen.generate_index_create_query(namespace=collection_namespace, defer_build=self.defer_build)
            self.run_cbq_query(query=query)
            if self.defer_build:
                query = index_gen.generate_build_query(collection_namespace)
                self.run_cbq_query(query=query)
            self.wait_until_indexes_online(defer_build=self.defer_build)

            # Validating index partition
            index_metadata = self.rest.get_indexer_metadata()['status']
            for index in index_metadata:
                if index['name'] != arr_index:
                    continue
                self.assertTrue(index['partitioned'], f"{arr_index} is not a partitioned index")
                self.assertEqual(index['numPartition'], 8, "No. of partitions are not matching")

            # Run a query that uses partitioned indexes
            query = f'select count(*) from {collection_namespace}  where join_mo > 3 and join_day > 15'
            result = self.run_cbq_query(query=query)['results'][0]['$1']
            self.assertNotEqual(result, 0)

            query = f'explain {query}'
            result = self.run_cbq_query(query=query)['results']
            self.assertEqual(result[0]['plan']['~children'][0]['index'], 'arr_index',
                             f"index arr_index is not used. Index used is {result[0]['plan']['~children'][0]['index']}")
            # Dropping the indexer
            query = index_gen.generate_index_drop_query(namespace=collection_namespace)
            self.run_cbq_query(query=query)

            # Creating partial partitioned index
            query = index_gen.generate_index_create_query(namespace=collection_namespace, defer_build=self.defer_build,
                                                          index_where_clause="test_rate > 5")
            self.run_cbq_query(query=query)
            if self.defer_build:
                query = index_gen.generate_build_query(collection_namespace)
                self.run_cbq_query(query=query)
            self.wait_until_indexes_online(defer_build=self.defer_build)

            # Validating index partition
            index_metadata = self.rest.get_indexer_metadata()['status']
            for index in index_metadata:
                if index['name'] != arr_index:
                    continue
                self.assertTrue(index['partitioned'], f"{arr_index} is not a partitioned index")
                self.assertEqual(index['numPartition'], 8, "No. of partitions are not matching")

            # Run a query that uses partitioned indexes
            query = f'select count(*) from {collection_namespace}  where join_mo > 3 and join_day > 15' \
                    f' and test_rate > 5'
            result = self.run_cbq_query(query=query)['results'][0]['$1']
            self.assertNotEqual(result, 0)

            query = f'explain {query}'
            result = self.run_cbq_query(query=query)['results']
            self.assertEqual(result[0]['plan']['~children'][0]['index'], 'arr_index',
                             f"index arr_index is not used. Index used is {result[0]['plan']['~children'][0]['index']}")
            # Dropping the indexer
            query = index_gen.generate_index_drop_query(namespace=collection_namespace)
            self.run_cbq_query(query=query)
        except Exception as err:
            query = index_gen.generate_index_drop_query(namespace=collection_namespace)
            self.run_cbq_query(query=query)
            self.fail(str(err))
        finally:
            query = primary_gen.generate_index_drop_query(namespace=collection_namespace)
            self.run_cbq_query(query=query)

    def test_partial_indexes(self):
        self._prepare_collection_for_indexing(json_template="Employee")
        collection_namespace = self.namespace[0]
        arr_index = "arr_index"
        primary_gen = QueryDefinition(index_name='`#primary`')
        index_gen = QueryDefinition(index_name=arr_index, index_fields=['join_mo', 'join_day'])
        try:
            query = primary_gen.generate_primary_index_create_query(namespace=collection_namespace,
                                                                    deploy_node_info=self.deploy_node_info,
                                                                    defer_build=self.defer_build,
                                                                    num_replica=self.num_index_replicas)

            self.run_cbq_query(query=query)
            if self.defer_build:
                query = primary_gen.generate_build_query(collection_namespace)
                self.run_cbq_query(query=query)
            self.wait_until_indexes_online(defer_build=self.defer_build)

            # Creating Partial index
            query = index_gen.generate_index_create_query(namespace=collection_namespace, defer_build=self.defer_build,
                                                          index_where_clause="join_yr > 2010")
            self.run_cbq_query(query=query)
            if self.defer_build:
                query = index_gen.generate_build_query(collection_namespace)
                self.run_cbq_query(query=query)
            self.wait_until_indexes_online(defer_build=self.defer_build)

            query = f"select count(*) from {collection_namespace} where join_mo > 8 and join_day > 15 and" \
                    f" join_yr > 2010"
            result = self.run_cbq_query(query=query)['results'][0]['$1']
            self.assertNotEqual(result, 0)

            query = f'Explain {query}'
            result = self.run_cbq_query(query=query)['results']
            self.assertEqual(result[0]['plan']['~children'][0]['index'], arr_index,
                             f'index {arr_index} is not used.')
            # Dropping the indexer
            query = index_gen.generate_index_drop_query(namespace=collection_namespace)
            self.run_cbq_query(query=query)

        except Exception as err:
            query = index_gen.generate_index_drop_query(namespace=collection_namespace)
            self.run_cbq_query(query=query)
            self.fail(str(err))
        finally:
            query = primary_gen.generate_index_drop_query(namespace=collection_namespace)
            self.run_cbq_query(query=query)

    def test_same_name_indexes(self):
        # todo: Untestested test - MB-40263
        # different scopes, different named collections
        num_combo = 2
        collection_prefix = 'test_collection'
        scope_prefix = 'test_scope'
        collection_namespaces = []
        arr_index = 'arr_index'
        index_gen = QueryDefinition(index_name=arr_index, index_fields=['age'])
        for item in range(num_combo):
            scope = f"{scope_prefix}_{item}"
            collection = f"{collection_prefix}_{item}"
            self.cli_rest.create_scope_collection(bucket=self.test_bucket, scope=scope, collection=collection)
            col_namespace = f"default:{self.test_bucket}.{scope}.{collection}"
            collection_namespaces.append(col_namespace)
            self.gen_create = SDKDataLoader(num_ops=1000, percent_create=100,
                                            percent_update=0, percent_delete=0, scope=scope, collection=collection)
            self._load_all_buckets(self.master, self.gen_create)
            query = index_gen.generate_index_create_query(namespace=col_namespace)
            self.run_cbq_query(query=query)
            self.wait_until_indexes_online()

        for col_namespace in collection_namespaces:
            _, keyspace = col_namespace.split(':')
            bucket, scope, collection = keyspace.split('.')
            try:
                # running a query that would use above index
                query = f"Select count(*) from {col_namespace} where age > 40"
                result = self.run_cbq_query(query=query)['results'][0]['$1']
                self.assertNotEqual(result, 0)

                query = f"Explain {query}"
                result = self.run_cbq_query(query=query)['results']
                self.assertEqual(result[0]['plan']['~children'][0]['index'], arr_index,
                                 f'index {arr_index} is not used.')
                query = index_gen.generate_index_drop_query(namespace=col_namespace)
                self.run_cbq_query(query=query)
                self.cli_rest.delete_scope_collection(bucket=bucket, scope=scope, collection=collection)
            except Exception as err:
                query = index_gen.generate_index_drop_query(namespace=col_namespace)
                self.run_cbq_query(query=query)
                self.fail(str(err))

        # different scopes, same named collection
        num_scope = 2
        collection = 'test_collection'
        collection_namespaces = []
        for item in range(num_scope):
            scope = f"scope_{item}"
            self.cli_rest.create_scope_collection(bucket=self.test_bucket, scope=scope, collection=collection)
            collection_namespaces.append(f"default:{self.test_bucket}.{scope}.{collection}")
            self.gen_create = SDKDataLoader(num_ops=1000, percent_create=100,
                                            percent_update=0, percent_delete=0, scope=scope, collection=collection)
            self._load_all_buckets(self.master, self.gen_create)
        for col_namespace in collection_namespaces:
            _, keyspace = col_namespace.split(':')
            bucket, scope, collection = keyspace.split('.')
            try:
                query = index_gen.generate_index_create_query(namespace=col_namespace)
                self.run_cbq_query(query=query)
                self.wait_until_indexes_online()

                # running a query that would use above index
                query = f"Select count(*) from {col_namespace} where age > 40"
                result = self.run_cbq_query(query=query)['results'][0]['$1']
                self.assertNotEqual(result, 0)

                query = f"Explain {query}"
                result = self.run_cbq_query(query=query)['results']
                self.assertEqual(result[0]['plan']['~children'][0]['index'], arr_index,
                                 f'index {arr_index} is not used.')
                query = index_gen.generate_index_drop_query(namespace=col_namespace)
                self.run_cbq_query(query=query)
                self.cli_rest.delete_scope_collection(bucket=bucket, scope=scope, collection=collection)
            except Exception as err:
                query = index_gen.generate_index_drop_query(namespace=col_namespace)
                self.run_cbq_query(query=query)
                self.fail(str(err))

        # Same scope, different named collections
        num_collection = 2
        scope = 'test_scope'
        collection_namespaces = []
        for item in range(num_collection):
            collection = f"collection_{item}"
            self.cli_rest.create_scope_collection(bucket=self.test_bucket, scope=scope, collection=collection)
            collection_namespaces.append(f"default:{self.test_bucket}.{scope}.{collection}")
            self.gen_create = SDKDataLoader(num_ops=1000, percent_create=100,
                                            percent_update=0, percent_delete=0, scope=scope, collection=collection)
            self._load_all_buckets(self.master, self.gen_create)
        for col_namespace in collection_namespaces:
            _, keyspace = col_namespace.split(':')
            bucket, scope, collection = keyspace.split('.')
            try:
                query = index_gen.generate_index_create_query(namespace=col_namespace)
                self.run_cbq_query(query=query)
                self.wait_until_indexes_online()

                # running a query that would use above index
                query = f"Select count(*) from {col_namespace} where age > 40"
                result = self.run_cbq_query(query=query)['results'][0]['$1']
                self.assertNotEqual(result, 0)

                query = f"Explain {query}"
                result = self.run_cbq_query(query=query)['results']
                self.assertEqual(result[0]['plan']['~children'][0]['index'], arr_index,
                                 f'index {arr_index} is not used.')
                query = index_gen.generate_index_drop_query(namespace=col_namespace)
                self.run_cbq_query(query=query)
                self.cli_rest.delete_scope_collection(bucket=bucket, scope=scope, collection=collection)
            except Exception as err:
                query = index_gen.generate_index_drop_query(namespace=col_namespace)
                self.run_cbq_query(query=query)
                self.fail(str(err))

    def test_build_indexes_at_different_stages(self):
        # todo: Incomplete test
        scope = 'test_scope'
        collection = 'test_collection'
        arr_index = 'arr_index'
        index_gen = QueryDefinition(index_name=arr_index, index_fields=['age'])
        primary_gen = QueryDefinition(index_name='`#primary`')
        self.cli_rest.create_scope_collection(bucket=self.test_bucket, scope=scope, collection=collection)
        collection_namespace = f"default:{self.test_bucket}.{scope}.{collection}"
        self.gen_create = SDKDataLoader(num_ops=10000, percent_create=100,
                                        percent_update=0, percent_delete=0, scope=scope, collection=collection)
        self._load_all_buckets(self.master, self.gen_create)
        query = primary_gen.generate_primary_index_create_query(namespace=collection_namespace)
        self.run_cbq_query(query=query)
        self.wait_until_indexes_online()

        query = f"select meta().id from {collection_namespace}"
        results = self.run_cbq_query(query=query)['results']
        doc_ids = [doc['id'] for doc in results]
        # building indexes during create operation

        # building indexes during upsert operation

        # building indexes during update operation

        # building indexes during delete operation

    def test_index_creation_with_increased_seq_num(self):
        """Create/Drop collection increment the seqno of a vbucket. It is important to test if indexer can handle those
         e.g. load docs in colA, create index idx1 on colA, create colB, build index idx1 on colA, drop colB,
         build index idx2 on colA etc. Try it with both empty collection and collection with mutations."""
        # todo: Incomplete test - MB-40288
        scope_prefix = 'test_scope'
        collection_prefix = 'test_collection'
        arr_index_1 = 'arr_index_1'
        arr_index_2 = 'arr_index_2'
        index_gen_1 = QueryDefinition(index_name=arr_index_1, index_fields=['age'])
        index_gen_2 = QueryDefinition(index_name=arr_index_2, index_fields=['city'])
        primary_gen = QueryDefinition(index_name='`#primary`')

        # creating colA and then creating index arr_index_1 on empty collection.
        # creating colB and then building index arr_index_1.
        # dropping colB and then creating index arr_index_2
        namespace = f"default:{self.test_bucket}.test_scope_1.test_col_1"
        try:
            self.cli_rest.create_scope_collection(bucket=self.test_bucket, scope='test_scope_1',
                                                  collection="test_col_1")
            self.sleep(5)
            query = primary_gen.generate_primary_index_create_query(namespace=namespace)
            self.run_cbq_query(query=query)
            query = index_gen_1.generate_index_create_query(namespace=namespace, defer_build=True)
            self.run_cbq_query(query=query)
            self.cli_rest.create_collection(bucket=self.test_bucket, scope='test_scope_1', collection="test_col_2")
            query = index_gen_1.generate_build_query(namespace=namespace)
            self.run_cbq_query(query=query)
            self.cli_rest.delete_collection(bucket=self.test_bucket,scope='test_scope_1', collection='test_col_2')
            self.wait_until_indexes_online()
            self.sleep(5)
            query = index_gen_2.generate_index_create_query(namespace=namespace)
            self.run_cbq_query(query=query)
            query = f'select count(*) from {namespace}'
            result = self.run_cbq_query(query=query)['results'][0]['$1']
            self.assertEqual(result, 0)
            query = index_gen_1.generate_index_drop_query(namespace=namespace)
            self.run_cbq_query(query=query)
            query = index_gen_2.generate_index_drop_query(namespace=namespace)
            self.run_cbq_query(query=query)

            # Trying with loaded collection
            self.cli_rest.create_collection(bucket=self.test_bucket, scope='test_scope_1', collection="test_col_2")
            self.gen_create = SDKDataLoader(num_ops=1000, percent_create=100, percent_update=0, percent_delete=0,
                                            scope='test_scope_1', collection='test_col_1')
            self._load_all_buckets(self.master, self.gen_create)
            query = index_gen_1.generate_index_create_query(namespace=namespace, defer_build=True)
            self.run_cbq_query(query=query)
            self.cli_rest.create_collection(bucket=self.test_bucket, scope='test_scope_1', collection="test_col_2")
            query = index_gen_1.generate_build_query(namespace=namespace)
            self.run_cbq_query(query=query)
            self.cli_rest.delete_collection(bucket=self.test_bucket,scope='test_scope_1', collection='test_col_2')
            self.wait_until_indexes_online()
            query = index_gen_2.generate_index_create_query(namespace=namespace)
            self.run_cbq_query(query=query)
            query = f'select count(*) from {namespace} where age > 0'
            result = self.run_query_with_retry(query=query, expected_result=1000, is_count_query=True)
            self.assertEqual(result, 1000)
            query = index_gen_1.generate_index_drop_query(namespace=namespace)
            self.run_cbq_query(query=query)
            query = index_gen_2.generate_index_drop_query(namespace=namespace)
            self.run_cbq_query(query=query)
        except Exception as err:
            self.log.error(str(err))
            query = index_gen_1.generate_index_drop_query(namespace=namespace)
            self.run_cbq_query(query=query)
            query = index_gen_2.generate_index_drop_query(namespace=namespace)
            self.run_cbq_query(query=query)
            self.fail()
