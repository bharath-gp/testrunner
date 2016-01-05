import httplib2
from tasks.taskmanager import TaskManager
from tasks.task import *


class ElasticSearchBase(object):

    def __init__(self, host, logger):
        #host is in the form IP address
        self.__log = logger
        self.__host = host
        self.__document = {}
        self.__mapping = {}
        self.__STATUSOK = 200
        self.__indices = []
        self.__index_types = {}
        self.__connection_url = 'http://{0}:{1}/'.format(self.__host.ip,
                                                        self.__host.port)
        self.es_queries = []
        self.task_manager = TaskManager("ES_Thread")
        self.task_manager.start()
        self.http = httplib2.Http

    def _http_request(self, api, method='GET', params='', headers=None,
                      timeout=30):
        if not headers:
            headers = {'Content-Type': 'application/json',
                       'Accept': '*/*'}
        try:
            response, content = httplib2.Http(timeout=timeout).request(api,
                                                                       method,
                                                                       params,
                                                                       headers)
            if response['status'] in ['200', '201', '202']:
                return True, content, response
            else:
                try:
                    json_parsed = json.loads(content)
                except ValueError as e:
                    json_parsed = {}
                    json_parsed["error"] = "status: {0}, content: {1}".\
                        format(response['status'], content)
                reason = "unknown"
                if "error" in json_parsed:
                    reason = json_parsed["error"]
                self.__log.error('{0} error {1} reason: {2} {3}'.format(
                    api,
                    response['status'],
                    reason,
                    content.rstrip('\n')))
                return False, content, response
        except socket.error as e:
            self.__log.error("socket error while connecting to {0} error {1} ".
                             format(api, e))
            raise ServerUnavailableException(ip=self.__host.ip)

    def is_running(self):
        """
         make sure ES is up and running
         check the service is running , if not abort the test
        """

        try:
            status, content, _ = self._http_request(
                self.__connection_url,
                'GET')
            if status:
                return True
            else:
                return False
        except Exception as e:
            raise e

    def delete_index(self, index_name):
        """
        Deletes index
        """
        try:
            url = self.__connection_url + index_name
            status, content, _ = self._http_request(url, 'DELETE')
        except Exception as e:
            raise e

    def delete_indices(self):
        """
        Delete all indices present
        """
        for index_name in self.__indices:
            self.delete_index(index_name)
            self.__log.info("ES index %s deleted" % index_name)

    def create_empty_index(self, index_name):
        """
        Creates an empty index, given the name
        """
        try:
            self.delete_index(index_name)
            status, content, _ = self._http_request(
                self.__connection_url + index_name,
                'PUT')
            if status:
                self.__indices.append(index_name)
        except Exception as e:
            raise Exception("Could not create ES index : %s" % e)

    def async_load_ES(self, index_name, gen, op_type='create'):
        """
        Asynchronously run query against FTS and ES and compare result
        note: every task runs a single query
        """

        _task = ESLoadGeneratorTask(es_instance=self,
                                    index_name=index_name,
                                    generator=gen,
                                    op_type=op_type)
        self.task_manager.schedule(_task)
        return _task

    def async_bulk_load_ES(self, index_name, gen, op_type='create', batch=5000):
        _task = ESBulkLoadGeneratorTask(es_instance=self,
                                    index_name=index_name,
                                    generator=gen,
                                    op_type=op_type,
                                    batch=batch)
        self.task_manager.schedule(_task)
        return _task

    def load_bulk_data(self, filename):
        """
        Bulk load to ES from a file
        curl -s -XPOST 172.23.105.25:9200/_bulk --data-binary @req
        cat req:
        { "index" : { "_index" : "default_es_index", "_type" : "aruna", "_id" : "1" } }
        { "field1" : "value1" , "field2" : "value2"}
        { "index" : { "_index" : "default_es_index", "_type" : "aruna", "_id" : "2" } }
        { "field1" : "value1" , "field2" : "value2"}
        """
        try:
            import os
            url = self.__connection_url + "/_bulk"
            data = open(filename, "rb").read()
            status, content, _ = self._http_request(url,
                                                    'POST',
                                                    data)
            return status
        except Exception as e:
            raise e

    def load_data(self, index_name, document_json, doc_type, doc_id):
        """
        index_name : name of index into which the doc is loaded
        document_json: json doc
        doc_type : type of doc. Usually the '_type' field in the doc body
        doc_id : document id
        """
        try:
            url = self.__connection_url + index_name + '/' + doc_type + '/' +\
                  doc_id
            status, content, _ = self._http_request(url,
                                                    'POST',
                                                    document_json)
        except Exception as e:
            raise e

    def update_index(self, index_name):
        """
        This procedure will refresh index when insert is performed .
        Need to call this API to take search in effect.
        :param index_name:
        :return:
        """
        try:
            status, content, _ = self._http_request(
                self.__connection_url + index_name +'/_refresh',
                'POST')
        except Exception as e:
            raise e

    def search(self, index_name, query, result_size=1000000):
        """
           This function will be used for search . based on the query
           :param index_name:
           :param query:
           :return: number of matches found, doc_ids and time taken
        """
        try:
            doc_ids = []
            url = self.__connection_url + index_name + '/_search?size='+ \
                  str(result_size)
            status, content, _ = self._http_request(
                url,
                'POST',
                json.dumps(query))
            if status:
                content = json.loads(content)
                for doc in content['hits']['hits']:
                    doc_ids.append(doc['_id'])
                return content['hits']['total'], doc_ids, content['took']
        except Exception as e:
            self.__log.error("Couldn't run query on ES: %s, reason : %s"
                             % (json.dumps(query), e))
            raise e

    def get_index_count(self, index_name):
        """
         Returns count of docs in the index
        """
        try:
            status, content, _ = self._http_request(
                self.__connection_url + index_name + '/_count',
                'POST')
            if status:
                return json.loads(content)['count']
        except Exception as e:
            raise e

    def get_indices(self):
        """
        Return all the indices created
        :return: List of all indices
        """
        return self.__indices
