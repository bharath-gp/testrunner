#!/usr/bin/env python
"""
Python based MySQL interface
"""
import mysql.connector
import zipfile
import os
from os.path import basename
import shutil
from mysql.connector import FieldType
from couchbase_helper.query_helper import QueryHelper

class MySQLClient(object):
    """Python MySQLClient Client Implementation for testrunner"""

    def __init__(self, database = None, host = "127.0.0.1", user_id = "root", password = ""):
        self.database = database
        self.host = host
        self.user_id = user_id
        self.password = password
        if self.database:
            self._set_mysql_client(self.database , self.host , self.user_id , self.password)
        else:
            self._set_mysql_client_without_database(self.host , self.user_id , self.password)

    def _reset_client_connection(self):
        self._close_mysql_connection()
        self._set_mysql_client(self.database , self.host , self.user_id , self.password)

    def _set_mysql_client(self, database = "flightstats", host = "127.0.0.1", user_id = "root", password = ""):
        self.mysql_connector_client = mysql.connector.connect(user = user_id, password = password,
         host = host, database = database)

    def _set_mysql_client_without_database(self, host = "127.0.0.1", user_id = "root", password = ""):
        self.mysql_connector_client = mysql.connector.connect(user = user_id, password = password,
         host = host)

    def _close_mysql_connection(self):
        self.mysql_connector_client.close()

    def _insert_execute_query(self, query = ""):
        cur = self.mysql_connector_client.cursor()
        try:
            cur.execute(query)
            self.mysql_connector_client.commit()
        except Exception, ex:
            print ex
            raise

    def _db_execute_query(self, query = ""):
        cur = self.mysql_connector_client.cursor()
        try:
            rows = cur.execute(query, multi = True)
            for row in rows:
                print row
        except Exception, ex:
            print ex
            raise

    def _execute_query(self, query = ""):
        column_names = []
        cur = self.mysql_connector_client.cursor()
        cur.execute(query)
        rows = cur.fetchall()
        desc = cur.description
        columns =[]
        for row in desc:
            columns.append({"column_name":row[0], "type":FieldType.get_info(row[1]).lower()})
        return columns, rows

    def _gen_json_from_results_with_primary_key(self, columns, rows, primary_key = ""):
        primary_key_index = 0
        count = 0
        dict = {}
        # Trace_index_of_primary_key
        for column in columns:
            if column["column_name"] == primary_key:
                primary_key_index = count
            count += 1
        # Convert to JSON and capture in a dictionary
        for row in rows:
            index = 0
            map = {}
            for column in columns:
                value = row[index]
                map[column["column_name"]] = self._convert_to_mysql_json_compatible_val(value, column["type"])
                index += 1
            dict[str(row[primary_key_index])] = map
        return dict

    def _gen_json_from_results(self, columns, rows):
        data = []
        # Convert to JSON and capture in a dictionary
        for row in rows:
            index = 0
            map = {}
            for column in columns:
                value = row[index]
                map[column["column_name"]] = self._convert_to_mysql_json_compatible_val(value, column["type"])
                index += 1
            data.append(map)
        return data

    def _convert_to_mysql_json_compatible_val(self, value, type):
        if isinstance(value, float):
            return round(value, 0)
        if "tiny" in str(type):
            if value == 0:
                return False
            else:
                return True
        if "int" in str(type):
            return value
        if "long" in str(type):
            return value
        if "datetime" in str(type):
            return str(value)
        if ("float" in str(type)) or ("double" in str(type)):
            if value == None:
                return None
            else:
                return round(value, 0)
        if "decimal" in str(type):
            if value == None:
                return None
            else:
                if isinstance(value, float):
                    return round(value, 0)
                return int(round(value, 0))
        return unicode(value)

    def _get_table_list(self):
        table_list = []
        columns, rows = self._execute_query(query = "SHOW TABLES")
        for row in rows:
            table_list.append(row[0])
        return table_list

    def _get_databases(self):
        table_list = []
        columns, rows = self._execute_query(query = "SHOW DATABASES")
        for row in rows:
            if "table" in row[0]:
                table_list.append(row[0])
        return table_list

    def _get_table_info(self, table_name = ""):
        columns, rows = self._execute_query(query = "DESCRIBE {0}".format(table_name))
        return self._gen_json_from_results(columns, rows)

    def _get_tables_information(self):
        map ={}
        list = self._get_table_list()
        for table_name in list:
            map[table_name] = self._get_table_info(table_name)
        return map

    def _get_field_list_map_for_tables(self):
        target_map = {}
        map = self._get_tables_information()
        for table_name in map.keys():
            field_list = []
            for field_info in map[table_name]:
                field_list.append(field_info['Field'])
            target_map[table_name] = field_list
        return target_map

    def _get_field_with_types_list_map_for_tables(self):
        target_map = {}
        map = self._get_tables_information()
        for table_name in map.keys():
            field_list = []
            for field_info in map[table_name]:
                field_list.append({field_info['Field']:field_info['Type']})
            target_map[table_name] = field_list
        return target_map

    def _get_primary_key_map_for_tables(self):
        target_map = {}
        map = self._get_tables_information()
        for table_name in map.keys():
            for field_info in map[table_name]:
                if field_info['Key'] == "PRI":
                    target_map[table_name] = field_info['Field']
        return target_map


    def _gen_index_combinations_for_tables(self, index_type = "GSI"):
        import itertools
        index_map = {}
        map = self._get_pkey_map_for_tables_without_primary_key_column()
        for table_name in map.keys():
            index_map[table_name] = {}
            number_field_list =[]
            string_field_list = []
            datetime_field_list= []
            for key in map[table_name].keys():
                if "int" in key or "decimal" in key:
                    number_field_list.append(key)
                if "char" in key or "text" in key:
                    string_field_list.append(key)
                if "tinyint" in key:
                    datetime_field_list.append(key)
            key_list = map[table_name].keys()
            count = 0
            index_list_map = {}
            prefix= table_name+"_idx_"
            for pair in list(itertools.permutations(key_list,1)):
                index_list_map[prefix+"_".join(pair)] = pair
            for pair in list(itertools.permutations(key_list,3)):
                index_list_map[prefix+"_".join(pair)] = pair
            for pair in list(itertools.permutations(string_field_list,len(string_field_list))):
                index_list_map[prefix+"_".join(pair)] = pair
            for pair in list(itertools.permutations(number_field_list,len(number_field_list))):
                index_list_map[prefix+"_".join(pair)] = pair
            index_list_map[prefix+"_".join(key_list)] = key_list
            index_map[table_name] = index_list_map
            index_list_map = {}
            final_map = {}
            for table_name in index_map.keys():
                final_map[table_name] = {}
                for index_name in index_map[table_name].keys():
                    defintion  = "CREATE INDEX {0} ON {1}({2}) USING {3}".format(index_name,table_name, ",".join(index_map[table_name][index_name]),index_type)
                    final_map[table_name][index_name] =\
                        {
                            "type":index_type,
                            "definition":defintion,
                            "name":index_name
                        }
        return final_map


    def _get_pkey_map_for_tables_with_primary_key_column(self):
        target_map = {}
        map = self._get_tables_information()
        number_of_tables = len(map.keys())
        count = 1
        for table_name in map.keys():
            target_map[table_name] ={}
            field_map = {}
            primary_key_field = "primary_key_field"
            for field_info in map[table_name]:
                field_map[field_info['Field']] ={"type":field_info['Type']}
                if field_info['Key'] == "PRI":
                    primary_key_field = field_info['Field']
            target_map[table_name]["fields"] = field_map
            target_map[table_name]["primary_key_field"] = primary_key_field
            if number_of_tables > 1:
                table_name_alias = "t_"+str(count)
                target_map[table_name]["alias_name"] = table_name_alias
            count += 1
        return target_map

    def _get_pkey_map_for_tables_without_primary_key_column(self):
        target_map = {}
        map = self._get_tables_information()
        for table_name in map.keys():
            target_map[table_name] ={}
            field_map = {}
            for field_info in map[table_name]:
                if field_info['Key'] != "PRI":
                    field_map[field_info['Field']] ={"type":field_info['Type']}
            target_map[table_name] = field_map
        return target_map

    def _get_pkey_map_for_tables_wit_primary_key_column(self):
        target_map = {}
        map = self._get_tables_information()
        for table_name in map.keys():
            target_map[table_name] ={}
            field_map = {}
            for field_info in map[table_name]:
                field_map[field_info['Field']] ={"type":field_info['Type']}
            target_map[table_name] = field_map
        return target_map

    def _get_distinct_values_for_fields(self, table_name, field):
        query = "Select DISTINCT({0}) from {1} ORDER BY {0}".format(field, table_name)
        list = []
        columns, rows = self._execute_query(query)
        for row in rows:
            list.append(row[0])
        return list

    def _get_values_with_type_for_fields_in_table(self):
        map = self._get_field_with_types_list_map_for_tables()
        gen_map = self._get_pkey_map_for_tables_with_primary_key_column()
        for table_name in map.keys():
            for vals in map[table_name]:
                field_name = vals.keys()[0]
                value_list = self._get_distinct_values_for_fields(table_name, field_name)
                gen_map[table_name]["fields"][field_name]["distinct_values"]= sorted(value_list)
        return gen_map

    def _gen_data_simple_table(self, number_of_rows = 1000):
        helper = QueryHelper()
        map = self._get_pkey_map_for_tables_wit_primary_key_column()
        for table_name in map.keys():
            for x in range(0, number_of_rows):
                statement = helper._generate_insert_statement(table_name, map[table_name])
                self._insert_execute_query(statement)

    def _gen_queries_from_template(self, query_path = "./queries.txt", table_name = "simple_table"):
        helper = QueryHelper()
        map = self._get_values_with_type_for_fields_in_table()
        table_map = map[table_name]
        with open(query_path) as f:
            content = f.readlines()
        for query in content:
            n1ql = helper._convert_sql_template_to_value(sql = query, table_map = table_map, table_name= table_name)

    def _query_and_convert_to_json(self, query):
        columns, rows = self._execute_query(query = query)
        sql_result = self._gen_json_from_results(columns, rows)
        return sql_result

    def _convert_template_query_info_with_gsi(self, file_path, gsi_index_file_path = None, table_map= {}, table_name = "simple_table", define_gsi_index = True, gen_expected_result = False):
        helper = QueryHelper()
        f = open(gsi_index_file_path,'w')
        n1ql_queries = self._read_from_file(file_path)
        for n1ql_query in n1ql_queries:
            check = True
            if not helper._check_deeper_query_condition(n1ql_query):
                if "SUBQUERY" in n1ql_query:
                    map = helper._convert_sql_template_to_value_with_subqueries(
                        n1ql_query, table_map = table_map, define_gsi_index= define_gsi_index)
                else:
                    map=helper._convert_sql_template_to_value_for_secondary_indexes(
                        n1ql_query, table_map = table_map, table_name = table_name, define_gsi_index= define_gsi_index)
            else:
                map=helper._convert_sql_template_to_value_for_secondary_indexes_sub_queries(
                    n1ql_query, table_map = table_map, table_name = table_name, define_gsi_index= define_gsi_index)
            if gen_expected_result:
                query = map["sql"]
                try:
                    sql_result = self._query_and_convert_to_json(query)
                    map["expected_result"] = sql_result
                except Exception, ex:
                    print ex
                    check = False
            if check:
                f.write(json.dumps(map)+"\n")
        f.close()

    def _convert_template_query_info(self, n1ql_queries = [], table_map= {}, define_gsi_index = True, gen_expected_result = False):
        helper = QueryHelper()
        query_input_list = []
        for n1ql_query in n1ql_queries:
            check = True
            if not helper._check_deeper_query_condition(n1ql_query):
                if "SUBQUERY" in n1ql_query:
                    map = helper._convert_sql_template_to_value_with_subqueries(
                    n1ql_query, table_map = table_map, define_gsi_index= define_gsi_index)
                else:
                    map=helper._convert_sql_template_to_value_for_secondary_indexes(
                    n1ql_query, table_map = table_map, define_gsi_index= define_gsi_index)
            else:
                map=helper._convert_sql_template_to_value_for_secondary_indexes_sub_queries(
                    n1ql_query, table_map = table_map, define_gsi_index= define_gsi_index)
            if gen_expected_result:
                query = map["sql"]
                try:
                    sql_result = self._query_and_convert_to_json(query)
                    map["expected_result"] = sql_result
                except Exception, ex:
                    print ex
                    check = False
            query_input_list.append(map)
        return query_input_list

    def  _read_from_file(self, file_path):
        with open(file_path) as f:
            content = f.readlines()
        return content

    def drop_database(self, database):
        query ="DROP SCHEMA IF EXISTS {0}".format(database)
        self._db_execute_query(query)

    def remove_databases(self):
        list_databases = self._get_databases()
        for database in list_databases:
            self.drop_database(database)

    def reset_database_add_data(self, database = "", items = 1000, sql_file_definiton_path= "/tmp/definition.sql"):
        sqls = self._read_from_file(sql_file_definiton_path)
        sqls = " ".join(sqls).replace("DATABASE_NAME",database).replace("\n","")
        self._db_execute_query(sqls)
        self.database = database
        self._reset_client_connection()
        self._gen_data_simple_table(number_of_rows = items)

    def dump_database(self, data_dump_path = "/tmp"):
        zip_path= data_dump_path+"/"+self.database+".zip"
        data_dump_path = data_dump_path+"/"+self.database
        os.mkdir(data_dump_path)
        table_key_map = self._get_primary_key_map_for_tables()
        # Make a list of buckets that we want to create for querying
        bucket_list = table_key_map.keys()
        # Read Data from mysql database and populate the couchbase server
        for bucket_name in bucket_list:
            query = "select * from {0}".format(bucket_name)
            columns, rows = self._execute_query(query = query)
            dict = self._gen_json_from_results_with_primary_key(columns, rows, table_key_map[bucket_name])
            # Take snap-shot of Data in
            f = open(data_dump_path+"/"+bucket_name+".txt",'w')
            f.write(json.dumps(dict))
            f.close()
        zipf = zipfile.ZipFile(zip_path, 'w')
        for root, dirs, files in os.walk(data_dump_path):
            for file in files:
                path = os.path.join(root, file)
                filter_path = path.replace(self.database,"")
                zipf.write(path, basename(filter_path))
        shutil.rmtree(data_dump_path)

    def _gen_gsi_index_info_from_n1ql_query_template(self, query_path = "./queries.txt", output_file_path = "./output.txt",  table_name = "simple_table", gen_expected_result= True):
        map = self._get_values_with_type_for_fields_in_table()
        table_map = map
        self._convert_template_query_info_with_gsi(query_path, gsi_index_file_path = output_file_path, table_map = table_map, table_name = table_name, gen_expected_result = gen_expected_result)

    def _gen_gsi_index_info_from_n1ql_query_template(self, query_path = "./queries.txt", output_file_path = "./output.txt",  table_name = "simple_table", gen_expected_result= True):
        map = self._get_values_with_type_for_fields_in_table()
        self._convert_template_query_info_with_gsi(query_path, gsi_index_file_path = output_file_path, table_map = map, gen_expected_result = gen_expected_result)

if __name__=="__main__":
    import json
    client = MySQLClient(host = "localhost", user_id = "root", password = "")
    #query = "select * from simple_table LIMIT 1"
    #print query
    #column_info, rows = client._execute_query(query = query)
    #dict = client._gen_json_from_results_with_primary_key(column_info, rows, "primary_key_id")
    #print dict
    #client.reset_database_add_data(database="multiple_table_db",sql_file_definiton_path = "/Users/parag/fix_testrunner/testrunner/b/resources/rqg/multiple_table_db/database_definition/definition.sql")
    client.remove_databases()
    #query_path="/Users/parag/fix_testrunner/testrunner/b/resources/rqg/simple_table/query_template/n1ql_query_template_10000.txt"
    #client.dump_database()
    #client._gen_gsi_index_info_from_n1ql_query_template(query_path="./temp.txt", gen_expected_result= False)
    #with open("./output.txt") as f:
    #    content = f.readlines()
    #for data in content:
    #    json_data= json.loads(data)
    #    print "<<<<<<<<<<< BEGIN >>>>>>>>>>"
    #    print json_data["sql"]
    #    print json_data["n1ql"]
    #    print json_data["gsi_indexes"]
    #    print "<<<<<<<<<<< END >>>>>>>>>>"
    #with open("./queries.txt") as f:
    #    content = f.readlines()
    #for sql in content:
    #    print " <<<<<< START >>>>>"
    #    print sql
    #    new_sql = helper._convert_sql_template_to_value(sql = sql, table_map = table_map, table_name= "airports")
    #    print new_sql
    #    print " <<<<< END >>>> "