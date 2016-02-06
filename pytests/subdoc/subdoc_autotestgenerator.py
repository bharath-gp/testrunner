from lib.mc_bin_client import MemcachedClient, MemcachedError
from lib.memcacheConstants import *
from lib.couchbase_helper.subdoc_helper import SubdocHelper
from lib.couchbase_helper.random_gen import RandomDataGenerator
from subdoc_base import SubdocBaseTest
import Queue
import copy, json
import threading
import random

class SubdocAutoTestGenerator(SubdocBaseTest):
    def setUp(self):
        super(SubdocAutoTestGenerator, self).setUp()
        self.verbose_func_usage =  self.input.param("verbose_func_usage",False)
        self.nesting_level =  self.input.param("nesting_level",0)
        self.mutation_operation_type =  self.input.param("mutation_operation_type","any")
        self.force_operation_type =  self.input.param("force_operation_type",None)
        self.run_data_verification =  self.input.param("run_data_verification",True)
        self.seed =  self.input.param("seed",0)
        self.run_mutation_mode =  self.input.param("run_mutation_mode","seq")
        self.client = self.direct_client(self.master, self.buckets[0])
        self.build_kv_store = self.input.param("build_kv_store", False)
        self.randomDataGenerator = RandomDataGenerator()
        self.subdoc_gen_helper = SubdocHelper()
        self.kv_store = {}

    def tearDown(self):
        super(SubdocAutoTestGenerator, self).tearDown()

    def test_readonly(self):
        self.client = self.direct_client(self.master, self.buckets[0])
    	error_result ={}
        data_set =  self.generate_json_for_nesting()
        base_json = self.generate_json_for_nesting()
        json_document = self.generate_nested(base_json, data_set, self.nesting_level)
        data_key = "test_readonly"
        self.set(self.client, data_key, json_document)
        pairs = {}
        self.subdoc_gen_helper.find_pairs(json_document,"", pairs)
        for path in pairs.keys():
            data = self.get(self.client, key = data_key, path = path)
            if data != pairs[path]:
            	error_result[path] = "expected {0}, actual = {1}".format(pairs[path], data)
        self.assertTrue(len(error_result) == 0, error_result)

    def test_exists(self):
        self.client = self.direct_client(self.master, self.buckets[0])
    	error_result ={}
        data_set =  self.generate_json_for_nesting()
        base_json = self.generate_json_for_nesting()
        json_document = self.generate_nested(base_json, data_set, self.nesting_level)
        data_key = "test_readonly"
        self.set(self.client, data_key, json_document)
        pairs = {}
        self.subdoc_gen_helper.find_pairs(json_document,"", pairs)
        for path in pairs.keys():
            try:
            	self.exists(self.client, data_key, path)
            except Exception, ex:
            	error_result[path] = str(ex)
        self.assertTrue(len(error_result) == 0, error_result)

    def test_seq_mutations_dict(self):
        self.mutation_operation_type = "dict"
        self.test_seq_mutations()

    def test_seq_mutations_array(self):
        self.mutation_operation_type = "array"
        self.test_seq_mutations()

    def test_seq_mutations(self):
        self.client = self.direct_client(self.master, self.buckets[0])
        error_result = {}
        self.number_of_operations =  self.input.param("number_of_operations",10)
        data_set =  self.generate_json_for_nesting()
        base_json = self.generate_json_for_nesting()
        json_document = self.generate_nested(base_json, data_set, self.nesting_level)
        data_key = "test_mutation_operations"
        self.set(self.client, data_key, json_document)
        operations = self.subdoc_gen_helper.build_sequence_operations(json_document, self.number_of_operations, seed = self.seed,
         mutation_operation_type = self.mutation_operation_type,
         force_operation_type = self.force_operation_type)
        for operation in operations:
            function = getattr(self, operation["subdoc_api_function_applied"])
            try:
                data_value = operation["data_value"]
                if not self.use_sdk_client:
                    data_value = json.dumps(data_value)
                function(self.client, data_key, operation["new_path_impacted_after_mutation_operation"], data_value)
            except Exception, ex:
                for key in operation:
                    self.log.info(" {0} : {1}".format(key, operation[key]))
                raise
        pairs = {}
        self.subdoc_gen_helper.find_pairs(json_document,"", pairs)
        for path in pairs.keys():
            data = self.get(self.client, key = data_key, path = path)
            if data != pairs[path]:
                error_result[path] = "expected {0}, actual = {1}".format(pairs[path], data)
        self.assertTrue(len(error_result) == 0, error_result)

    def test_concurrent_mutations_dict(self):
        self.mutation_operation_type = "dict"
        self.test_concurrent_mutations()

    def test_concurrent_mutations_array(self):
        self.mutation_operation_type = "array"
        self.test_concurrent_mutations()

    def test_concurrent_mutations(self):
        randomDataGenerator = RandomDataGenerator()
        randomDataGenerator.set_seed(self.seed)
        base_json = randomDataGenerator.random_json()
        data_set = randomDataGenerator.random_json()
        json_document = self.generate_nested(base_json, data_set, self.nesting_level)
        data_key = "test_concurrent_mutations"
        self.run_mutation_concurrent_operations(self.buckets[0], data_key, json_document)

    def run_mutation_concurrent_operations(self, bucket = None, document_key = "", json_document = {}):
        client = self.direct_client(self.master, self.buckets[0])
        self.number_of_operations =  self.input.param("number_of_operations",10)
        # INSERT INTO  COUCHBASE
        self.set(client, document_key, json_document)
        # RUN PARALLEL OPERATIONS
        operations = self.subdoc_gen_helper.build_concurrent_operations(
            json_document, self.number_of_operations, seed = self.seed,
            mutation_operation_type = self.mutation_operation_type,
             force_operation_type = self.force_operation_type)
        # RUN CONCURRENT THREADS
        thread_list = []
        result_queue = Queue.Queue()
        self.log.info(" number of operations {0}".format(len(operations)))
        for operation in operations:
            client = self.direct_client(self.master, self.buckets[0])
            t = threading.Thread(target=self.run_mutation_operation, args = (client, document_key, operation, result_queue))
            t.daemon = True
            t.start()
            thread_list.append(t)
        for t in thread_list:
            t.join()
        queue_data = []
        while not result_queue.empty():
            queue_data.append(result_queue.get())
        self.assertTrue(len(queue_data) == 0, queue_data)
        # CHECK RESULT IN THE END
        json_document  = copy.deepcopy(operations[len(operations)-1]["mutated_data_set"])
        pairs = {}
        error_result = {}
        self.subdoc_gen_helper.find_pairs(json_document,"", pairs)
        for path in pairs.keys():
            data = self.get(client, document_key, path)
            if data != pairs[path]:
                error_result[path] = "expected {0}, actual = {1}".format(pairs[path], data)
        self.assertTrue(len(error_result) == 0, error_result)

    def run_mutation_operation(self, client, document_key, operation, result_queue):
        function = getattr(self, operation["subdoc_api_function_applied"])
        try:
            data_value  = operation["data_value"]
            if not self.use_sdk_client:
                data_value = json.dumps(data_value)
            function(client, document_key, operation["new_path_impacted_after_mutation_operation"], data_value)
        except Exception, ex:
            self.log.info(str(ex))
            result_queue.put({"error":str(ex),"operation_type":operation["subdoc_api_function_applied"]})

    ''' Generic Test case for running sequence operations based tests '''
    def test_mutation_operations(self):
        self.number_of_documents =  self.input.param("number_of_documents",10)
        self.number_of_operations =  self.input.param("number_of_operations",10)
        self.concurrent_threads =  self.input.param("num",10)
        error_queue = Queue.Queue()
        document_info_queue = Queue.Queue()
        thread_list = []
        # RUN INPUT FILE READ THREAD
        document_push = threading.Thread(target=self.push_document_info, args = (self.number_of_documents, document_info_queue))
        document_push.start()
        document_push.join()
        self.sleep(2)
        # RUN WORKER THREADS
        for x in range(self.concurrent_threads):
            t = threading.Thread(target=self.worker_operation_run, args = (document_info_queue, error_queue, self.buckets[0], self.mutation_operation_type, self.force_operation_type))
            t.daemon = True
            t.start()
            thread_list.append(t)
        for t in thread_list:
            t.join()
        # ERROR ANALYSIS
        error_msg =""
        error_count = 0
        if not error_queue.empty():
            # Dump Re-run file
            dump_file = open('/tmp/dump_failure.txt', 'wb')
            while not error_queue.empty():
                error_count+=1
                error_data = error_queue.get()
                self.log.info(" document_info {0}".format(error_data["document_info"]))
                self.log.info(" error_result {0}".format(error_data["error_result"]))
                dump_file.write(json.dumps(error_data["document_info"]))
            dump_file.close()
            # Fail the test with result count
            self.assertTrue(not error_queue.empty(), "error count {0}".format(error_count))

    ''' Generate Sample data for testing '''
    def push_document_info(self, number_of_documents, document_info_queue):
        for x in range(number_of_documents):
            document_info = {}
            randomDataGenerator = RandomDataGenerator()
            randomDataGenerator.set_seed(self.seed)
            document_info["seed"] = randomDataGenerator.random_int()
            base_json = randomDataGenerator.random_json()
            data_set = randomDataGenerator.random_json()
            json_document = self.generate_nested(base_json, data_set, self.nesting_level)
            document_info["json_document"] = json_document
            document_info_queue.put(document_info)

    ''' Worker for sequence operations on JSON '''
    def worker_operation_run(self,
        queue,
        error_queue,
        bucket,
        mutation_operation_type = "any",
        force_operation_type = None):
        client = self.direct_client(self.master, self.buckets[0])
        while (not queue.empty()):
            document_info = queue.get()
            json_document = document_info["json_document"]
            seed = document_info["seed"]
            document_key =  "document_key_"+str(self.randomDataGenerator.random_int())
            logic, error_result = self.run_mutation_operations(client, bucket,
                document_key= document_key, json_document = json_document, seed =  seed,
                number_of_operations = self.number_of_operations,
                mutation_operation_type = mutation_operation_type,
                force_operation_type = force_operation_type)
            if not logic:
                error_queue.put({"error_result":error_result, "document_info":document_info})

    ''' Method to run sequence operations for a given JSON document '''
    def run_mutation_operations(self,
        client,
        bucket,
        document_key = "document_key",
        json_document = {},
        seed = 0,
        number_of_operations = 10,
        mutation_operation_type = "any",
        force_operation_type = None):
        self.set(client, document_key, json_document)
        self.log.info(" START WORKING ON {0}".format(document_key))
        if self.run_mutation_mode == "seq":
            operations = self.subdoc_gen_helper.build_sequence_operations(
                json_document,
                max_number_operations = number_of_operations,
                seed = seed,
                mutation_operation_type = mutation_operation_type,
                force_operation_type = force_operation_type)
            self.log.info("TOTAL OPERATIONS CALCULATED {0} ".format(len(operations)))
            operation_index=1
            for operation in operations:
                function = getattr(self, operation["subdoc_api_function_applied"])
                try:
                    data_value = operation["data_value"]
                    if not self.use_sdk_client:
                        data_value = json.dumps(operation["data_value"])
                    function(client, document_key, operation["new_path_impacted_after_mutation_operation"], data_value)
                    operation_index+=1
                except Exception, ex:
                    self.log.info(str(ex))
                    raise
                    return False, operation
        else:
            logic, result = self.run_concurrent_mutation_operations(document_key, bucket, seed, json_document, number_of_operations, mutation_operation_type, force_operation_type)
            if not logic:
                return False, logic
        self.log.info(" END WORKING ON {0}".format(document_key))
        if self.build_kv_store:
            self.kv_store[document_key] = operations[len(operations)-1]["mutated_data_set"]
        error_result = {}
        if self.run_data_verification:
            pairs = {}
            self.subdoc_gen_helper.find_pairs(json_document,"", pairs)
            for path in pairs.keys():
                #self.log.info(" Analyzing path {0}".format(path))
                data = self.get(client, document_key, path)
                if data != pairs[path]:
                    error_result[path] = "expected {0}, actual = {1}".format(pairs[path], data)
            if len(error_result) != 0:
                return False, error_result
        return True, error_result

    def run_concurrent_mutation_operations(self, document_key, bucket, seed, json_document, number_of_operations, mutation_operation_type, force_operation_type):
        result_queue = Queue.Queue()
        operations = self.subdoc_gen_helper.build_concurrent_operations(
                json_document,
                max_number_operations = number_of_operations,
                seed = seed,
                mutation_operation_type = mutation_operation_type,
                force_operation_type = force_operation_type)
        self.log.info("TOTAL OPERATIONS CALCULATED {0} ".format(len(operations)))
        thread_list = []
        for operation in operations:
            client = self.direct_client(self.master, self.buckets[0])
            t = threading.Thread(target=self.run_mutation_operation, args = (client, document_key, operation, result_queue))
            t.daemon = True
            t.start()
            thread_list.append(t)
        for t in thread_list:
            t.join()
        if result_queue.empty():
            return True, None
        return False, result_queue


    ''' Method to verify kv store data set '''
    def run_verification(self, bucket, kv_store = {}):
        client = self.direct_client(self.master, self.buckets[0])
        error_result = {}
        for document_key in kv_store.keys():
            pairs = {}
            json_document = kv_store[document_key]
            self.subdoc_gen_helper.find_pairs(json_document,"", pairs)
            for path in pairs.keys():
                opaque, cas, data = client.get_sd(document_key, path)
                data = json.loads(data)
                if data != pairs[path]:
                    error_result[path] = "key = {0}, expected {1}, actual = {2}".format(document_key, pairs[path], data)
        self.assertTrue(len(error_result) != 0, error_result)

# DOC COMMANDS
    def set(self, client, key, value):
        try:
            if self.verbose_func_usage:
                self.log.info(" set ----> {0} ".format(key))
            if self.use_sdk_client:
                client.set(key, value)
            else:
                jsonDump = json.dumps(value)
                client.set(key, 0, 0, jsonDump)
        except Exception as e:
            raise
# SUB DOC COMMANDS

# GENERIC COMMANDS
    def delete(self, client, key = '', path = '', value = None):
        try:
            if self.verbose_func_usage:
                self.log.info(" delete ----> {0} ".format(path))
            if self.use_sdk_client:
                client.remove_in(key, path)
            else:
                client.delete_sd(key, path)
        except Exception as e:
            raise

    def replace(self, client, key = '', path = '', value = None):
        try:
            if self.verbose_func_usage:
                self.log.info(" replace ----> {0} :: {1}".format(path, value))
            if self.use_sdk_client:
                client.replace_in(key, path, value)
            else:
                client.replace_sd(key, path, value)
        except Exception as e:
            raise

    def get(self, client, key = '', path = '', value = None):
        try:
            if self.verbose_func_usage:
                self.log.info(" get ----> {0} :: {1}".format(key, path))
            if self.use_sdk_client:
                r, v, d = client.get_in(key, path)
                return d
            else:
                r, v, d = client.get_sd(key, path)
                return json.loads(d)
        except Exception as e:
            raise

    def exists(self, client, key = '', path = '', expected_value = None):
        try:
            if self.use_sdk_client:
                return client.exists_in(key, path)
            else:
                client.exists_sd(key, path)
        except Exception as e:
            raise

    def counter(self, client, key = '', path = '', value = None):
        try:
            if self.verbose_func_usage:
                self.log.info(" counter ----> {0} :: {1} + {2}".format(key, path, value))
            if self.use_sdk_client:
                return client.counter_in(key, path, value)
            else:
                client.counter_sd(key, path, value)
        except Exception as e:
            raise

# DICTIONARY SPECIFIC COMMANDS
    def dict_add(self, client, key = '', path = '', value = None):
        try:
            if self.verbose_func_usage:
                self.log.info(" dict_add ----> {0} :: {1}".format(path, value))
            if self.use_sdk_client:
                client.insert_in(key, path, value)
            else:
                client.dict_add_sd(key, path, value)
        except Exception as e:
            raise

    def dict_upsert(self, client, key = '', path = '', value = None):
        try:
            if self.verbose_func_usage:
                self.log.info(" dict_upsert ----> {0} :: {1}".format(path, value))
            if self.use_sdk_client:
                client.upsert_in(key, path, value)
            else:
                client.dict_upsert_sd(key, path, value)
        except Exception as e:
            raise


# ARRAY SPECIFIC COMMANDS
    def array_add_last(self, client, key = '', path = '', value = None):
        try:
            if self.verbose_func_usage:
                self.log.info(" array_add_last ----> {0} :: {1}".format(path, value))
            if self.use_sdk_client:
                client.arrayappend_in(key, path, value)
            else:
                client.array_push_last_sd(key, path, value)
        except Exception as e:
            raise

    def array_add_first(self, client, key = '', path = '', value = None):
        try:
            if self.verbose_func_usage:
                self.log.info(" array_add_first ----> {0} :: {1}".format(path, value))
            if self.use_sdk_client:
                client.arrayprepend_in(key, path, value)
            else:
                client.array_push_first_sd(key, path, value)
        except Exception as e:
            raise

    def array_add_unique(self, client, key = '', path = '', value = None):
        try:
            if self.verbose_func_usage:
                self.log.info(" array_add_unique ----> {0} :: {1}".format(path, value))
            if self.use_sdk_client:
                client.arrayaddunique_in(key, path, value)
            else:
                client.array_add_unique_sd(key, path, value)
        except Exception as e:
            raise

    def array_add_insert(self, client, key = '', path = '', value = None):
        try:
            if self.verbose_func_usage:
                self.log.info(" array_add_insert ----> {0} :: {1}".format(path, value))
            if self.use_sdk_client:
                client.arrayinsert_in(key, path, value)
            else:
                client.array_add_insert_sd(key, path, value)
        except Exception as e:
            raise
