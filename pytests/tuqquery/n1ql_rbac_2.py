import json

from TestInput import TestInputSingleton
from lib.membase.api.rest_client import RestConnection
from remote.remote_util import RemoteMachineShellConnection
from security.rbac_base import RbacBase
from tuq import QueryTests


class RbacN1QL(QueryTests):

    def setUp(self):
        super(RbacN1QL, self).setUp()
        users = TestInputSingleton.input.param("users", None)
        self.all_buckets = TestInputSingleton.input.param("all_buckets", False)
        print users
        self.inp_users = []
        if users:
            self.inp_users = eval(eval(users))
        self.users = self.get_user_list()
        self.roles = self.get_user_role_list()

    def tearDown(self):
        super(RbacN1QL, self).tearDown()

    def create_users(self, users=None):
        """
        :param user: takes a list of {'id': 'xxx', 'name': 'some_name ,
                                        'password': 'passw0rd'}
        :return: Nothing
        """
        if not users:
            users = self.users
        RbacBase().create_user_source(users,'builtin',self.master)
        self.log.info("SUCCESS: User(s) %s created"
                      % ','.join([user['name'] for user in users]))

    def assign_role(self, rest=None, roles=None):
        if not rest:
            rest = RestConnection(self.master)
        #Assign roles to users
        if not roles:
            roles = self.roles
        RbacBase().add_user_role(roles, rest,'builtin')
        for user_role in roles:
            self.log.info("SUCCESS: Role(s) %s assigned to %s"
                          %(user_role['roles'], user_role['id']))

    def delete_role(self, rest=None, user_ids=None):
        if not rest:
            rest = RestConnection(self.master)
        if not user_ids:
            user_ids = [user['id'] for user in self.roles]
        RbacBase().remove_user_role(user_ids, rest)
        self.sleep(20, "wait for user to get deleted...")
        self.log.info("user roles revoked for %s" % ", ".join(user_ids))

    def get_user_list(self):
        """
        :return:  a list of {'id': 'userid', 'name': 'some_name ,
        'password': 'passw0rd'}
        """
        user_list = []
        for user in self.inp_users:
            user_list.append({att: user[att] for att in ('id',
                                                         'name',
                                                         'password')})
        return user_list

    def get_user_role_list(self):
        """
        :return:  a list of {'id': 'userid', 'name': 'some_name ,
         'roles': 'admin:fts_admin[default]'}
        """
        user_role_list = []
        for user in self.inp_users:
            user_role_list.append({att: user[att] for att in ('id',
                                                              'name',
                                                              'roles')})
        return user_role_list

    def retrieve_roles(self):
        server = self.master
        rest = RestConnection(server)
        url = "/settings/rbac/roles"
        api = rest.baseUrl + url
        status, content, header = rest._http_request(api, 'GET')
        self.log.info(" Retrieve all User roles - Status - {0} -- Content - {1} -- Header - {2}".format(status, content, header))
        return status, content, header

    def retrieve_users(self):
        rest = RestConnection(self.master)
        url = "/settings/rbac/users"
        api = rest.baseUrl + url
        status, content, header = rest._http_request(api, 'GET')
        self.log.info(" Retrieve User Roles - Status - {0} -- Content - {1} -- Header - {2}".format(status, content, header))
        return status, content, header

    def grant_role(self, role=None):
        if not role:
            role = self.roles[0]['roles']
            if self.all_buckets:
                role += "(`*`)"
        self.query = "GRANT ROLE {0} to {1}".format(role, self.users[0]['id'])
        actual_result = self.run_cbq_query()
        self.assertTrue(actual_result['status'] == 'success', "Unable to grant role {0} to {1}".
                                                                format(role, self.users[0]['id']))

    def revoke_role(self, role=None):
        if not role:
            role = self.roles[0]['roles']
            if self.all_buckets:
                role += "(`*`)"
        self.query = "REVOKE ROLE {0} FROM {1}".format(role, self.users[0]['id'])
        actual_result = self.run_cbq_query()
        self.assertTrue(actual_result['status'] == 'success', "Unable to revoke role {0} from {1}".
                                                                format(role, self.users[0]['id']))

    def test_select(self):
        self.create_users()
        self.shell.execute_command("killall cbq-engine")
        self.grant_role()
        shell = RemoteMachineShellConnection(self.master)
        cmd = "curl -u {0}:{1} http://{2}:8093/query/service -d 'statement=SELECT * from {3} LIMIT 10'".\
                format(self.users[0]['id'], self.users[0]['password'], self.master.ip, self.buckets[0].name)
        output, error = shell.execute_command(cmd)
        shell.log_command_output(output, error)
        self.assertTrue(any("success" in line for line in output), "Unable to select from {0} as user {1}".
                        format(self.buckets[0].name, self.users[0]['id']))
        self.log.info("Query executed successfully")

    def test_update(self):
        self.create_users()
        self.shell.execute_command("killall cbq-engine")
        self.grant_role()
        shell = RemoteMachineShellConnection(self.master)
        old_name = "employee-14"
        new_name = "employee-14-2"
        cmd = "curl -u {0}:{1} http://{2}:8093/query/service -d " \
              "'statement=UPDATE {3} a set name = '{4}' where name = '{5}' limit 1'".\
                format(self.users[0]['id'], self.users[0]['password'], self.master.ip, self.buckets[0].name, new_name, old_name)
        output, error = shell.execute_command(cmd)
        shell.log_command_output(output, error)
        self.assertTrue(any("success" in line for line in output), "Unable to update from {0} as user {1}".
                        format(self.buckets[0].name, self.users[0]['id']))
        self.log.info("Query executed successfully")

    def test_insert(self):
        self.create_users()
        self.shell.execute_command("killall cbq-engine")
        self.grant_role()
        shell = RemoteMachineShellConnection(self.master)
        cmd = "curl -u %s:%s http://%s:8093/query/service -d " \
              "'statement=INSERT INTO %s (KEY, VALUE) VALUES(\"1\", { \"value1\": \"one1\" })'"%\
                (self.users[0]['id'], self.users[0]['password'], self.master.ip, self.buckets[0].name)
        output, error = shell.execute_command(cmd)
        shell.log_command_output(output, error)
        self.assertTrue(any("success" in line for line in output), "Unable to insert into {0} as user {1}".
                        format(self.buckets[0].name, self.users[0]['id']))
        self.log.info("Query executed successfully")

    def test_delete(self):
        self.create_users()
        self.shell.execute_command("killall cbq-engine")
        self.grant_role()
        shell = RemoteMachineShellConnection(self.master)
        del_name = "employee-14"
        cmd = "curl -u {0}:{1} http://{2}:8093/query/service -d " \
              "'statement=DELETE FROM {3} a WHERE name = '{4}''".\
                format(self.users[0]['id'], self.users[0]['password'], self.master.ip, self.buckets[0].name, del_name)
        output, error = shell.execute_command(cmd)
        shell.log_command_output(output, error)
        self.assertTrue(any("success" in line for line in output), "Unable to delete from {0} as user {1}".
                        format(self.buckets[0].name, self.users[0]['id']))
        self.log.info("Query executed successfully")

    def test_upsert(self):
        self.create_users()
        self.shell.execute_command("killall cbq-engine")
        self.grant_role()
        shell = RemoteMachineShellConnection(self.master)
        cmd = "curl -u %s:%s http://%s:8093/query/service -d " \
              "'statement=UPSERT INTO %s (KEY, VALUE) VALUES(\"1\", { \"value1\": \"one1\" }) RETURNING *'"%\
                (self.users[0]['id'], self.users[0]['password'], self.master.ip, self.buckets[0].name)
        output, error = shell.execute_command(cmd)
        shell.log_command_output(output, error)
        self.assertTrue(any("success" in line for line in output), "Unable to upsert into {0} as user {1}".
                        format(self.buckets[0].name, self.users[0]['id']))
        self.log.info("Query executed successfully")

    def test_merge(self):
        self.create_users()
        self.shell.execute_command("killall cbq-engine")
        self.grant_role()
        shell = RemoteMachineShellConnection(self.master)
        cmd = "curl -u %s:%s http://%s:8093/query/service -d " \
              "'statement=MERGE INTO %s b1 USING %s b2 ON KEY b2.%s WHEN NOT MATCHED THEN " \
              "INSERT { \"value1\": \"one1\" }'"%\
                (self.users[0]['id'], self.users[0]['password'], self.master.ip, self.buckets[0].name, self.buckets[1].name, 'name')
        output, error = shell.execute_command(cmd)
        shell.log_command_output(output, error)
        self.assertTrue(any("success" in line for line in output), "Unable to merge {0} and {1} as user {2}".
                        format(self.buckets[0].name, self.buckets[1].name, self.users[0]['id']))
        self.log.info("Query executed successfully")

    def test_create_build_index(self):
        self.create_users()
        self.shell.execute_command("killall cbq-engine")
        self.grant_role()
        shell = RemoteMachineShellConnection(self.master)
        cmd = "curl -u %s:%s http://%s:8093/query/service -d " \
              "'statement=CREATE INDEX `age-index` ON %s(age) USING GSI WITH {\"defer_build\":true}'"%\
                (self.users[0]['id'], self.users[0]['password'], self.master.ip, self.buckets[0].name)
        output, error = shell.execute_command(cmd)
        shell.log_command_output(output, error)
        self.assertTrue(any("success" in line for line in output), "Unable to create index on {0} as user {1}".
                        format(self.buckets[0].name, self.users[0]['id']))
        self.log.info("Create Query executed successfully")
        cmd = "curl -u %s:%s http://%s:8093/query/service -d " \
              "'statement=BUILD INDEX ON %s(`age-index`) USING GSI'"%\
                (self.users[0]['id'], self.users[0]['password'], self.master.ip, self.buckets[0].name)
        output, error = shell.execute_command(cmd)
        shell.log_command_output(output, error)
        self.assertTrue(any("success" in line for line in output), "Unable to build index on {0} as user {1}".
                        format(self.buckets[0].name, self.users[0]['id']))
        self.log.info("Build Query executed successfully")

    def test_create_drop_index(self):
        self.create_users()
        self.shell.execute_command("killall cbq-engine")
        self.grant_role()
        shell = RemoteMachineShellConnection(self.master)
        cmd = "curl -u %s:%s http://%s:8093/query/service -d " \
              "'statement=CREATE INDEX `age-index` ON %s(age) USING GSI'"%\
                (self.users[0]['id'], self.users[0]['password'], self.master.ip, self.buckets[0].name)
        output, error = shell.execute_command(cmd)
        shell.log_command_output(output, error)
        self.assertTrue(any("success" in line for line in output), "Unable to create index on {0} as user {1}".
                        format(self.buckets[0].name, self.users[0]['id']))
        self.log.info("Create Query executed successfully")
        cmd = "curl -u %s:%s http://%s:8093/query/service -d " \
              "'statement=DROP INDEX %s.`age-index` USING GSI'"%\
                (self.users[0]['id'], self.users[0]['password'], self.master.ip, self.buckets[0].name)
        output, error = shell.execute_command(cmd)
        shell.log_command_output(output, error)
        self.assertTrue(any("success" in line for line in output), "Unable to build index on {0} as user {1}".
                        format(self.buckets[0].name, self.users[0]['id']))
        self.log.info("Drop Query executed successfully")

    def test_prepare(self):
        self.create_users()
        self.shell.execute_command("killall cbq-engine")
        self.grant_role()
        shell = RemoteMachineShellConnection(self.master)
        cmd = "curl -u {0}:{1} http://{2}:8093/query/service -d 'statement=PREPARE SELECT * from {3} LIMIT 10'".\
                format(self.users[0]['id'], self.users[0]['password'], self.master.ip, self.buckets[0].name)
        output, error = shell.execute_command(cmd)
        shell.log_command_output(output, error)
        self.assertTrue(any("success" in line for line in output), "Unable to prepare select from {0} as user {1}".
                        format(self.buckets[0].name, self.users[0]['id']))
        self.log.info("Prepare query executed successfully")

    def test_infer(self):
        self.create_users()
        self.shell.execute_command("killall cbq-engine")
        self.grant_role()
        shell = RemoteMachineShellConnection(self.master)
        cmd = "curl -u %s:%s http://%s:8093/query/service -d 'statement=INFER %s WITH {\"sample_size\":10,\"num_sample_values\":2}'"%\
                (self.users[0]['id'], self.users[0]['password'], self.master.ip, self.buckets[0].name)
        output, error = shell.execute_command(cmd)
        shell.log_command_output(output, error)
        self.assertTrue(any("success" in line for line in output), "Unable to infer from {0} as user {1}".
                        format(self.buckets[0].name, self.users[0]['id']))
        self.log.info("Infer query executed successfully")

    def test_explain(self):
        self.create_users()
        self.shell.execute_command("killall cbq-engine")
        self.grant_role()
        shell = RemoteMachineShellConnection(self.master)
        cmd = "curl -u {0}:{1} http://{2}:8093/query/service -d 'statement=EXPLAIN SELECT * from {3} LIMIT 10'".\
                format(self.users[0]['id'], self.users[0]['password'], self.master.ip, self.buckets[0].name)
        output, error = shell.execute_command(cmd)
        shell.log_command_output(output, error)
        self.assertTrue(any("success" in line for line in output), "Unable to explain select from {0} as user {1}".
                        format(self.buckets[0].name, self.users[0]['id']))
        self.log.info("Explain query executed successfully")

    def test_create_user_roles(self):
        self.create_users()
        self.shell.execute_command("killall cbq-engine")
        user = self.users[0]['id']
        role = self.roles[0]['roles']
        self.grant_role()
        _,content,_ = self.retrieve_users()
        content = json.loads(content)
        found = False
        for assignment in content:
            if assignment['id'] == user:
                for item in assignment['roles']:
                    if item['role'] == role:
                        found = True
                        break
        self.assertTrue(found, "{0} not granted role {1} as expected".format(user, role))
        self.log.info("{0} granted role {1} as expected".format(user, role))

    def test_update_user_roles(self):
        self.create_users()
        self.shell.execute_command("killall cbq-engine")
        user = self.users[0]['id']
        role = self.roles[0]['roles']
        self.grant_role()
        _,content,_ = self.retrieve_users()
        content = json.loads(content)
        found = False
        for assignment in content:
            if assignment['id'] == user:
                for item in assignment['roles']:
                    if item['role'] == role:
                        found = True
                        break
        self.assertTrue(found, "{0} not granted old role {1} as expected".format(user, role))
        self.log.info("{0} granted old role {1} as expected".format(user, role))
        self.revoke_role()
        new_role = TestInputSingleton.input.param("new_role", None)
        self.grant_role(role=new_role)
        _,content,_ = self.retrieve_users()
        content = json.loads(content)
        found = False
        for assignment in content:
            if assignment['id'] == user:
                for item in assignment['roles']:
                    if item['role'] == new_role:
                        found = True
                        break
        self.assertTrue(found, "{0} not granted new role {1} as expected".format(user, new_role))
        self.log.info("{0} granted new role {1} as expected".format(user, new_role))

    def test_delete_user_roles(self):
        self.create_users()
        self.shell.execute_command("killall cbq-engine")
        user = self.users[0]['id']
        role = self.roles[0]['roles']
        self.grant_role()
        _,content,_ = self.retrieve_users()
        content = json.loads(content)
        found = False
        for assignment in content:
            if assignment['id'] == user:
                for item in assignment['roles']:
                    if item['role'] == role:
                        found = True
                        break
        self.assertTrue(found, "{0} not granted role {1} as expected".format(user, role))
        self.log.info("{0} granted role {1} as expected".format(user, role))
        self.revoke_role()
        _,content,_ = self.retrieve_users()
        content = json.loads(content)
        found = False
        for assignment in content:
            if assignment['id'] == user:
                for item in assignment['roles']:
                    if item['role'] == role:
                        found = True
                        break
        self.assertFalse(found, "{0} not revoked of role {1} as expected".format(user, role))
        self.log.info("{0} revoked of role {1} as expected".format(user, role))

    def test_multiple_user_roles_listing(self):
        self.create_users()
        self.shell.execute_command("killall cbq-engine")
        user = self.users[0]['id']
        role = "query_select(default),bucket_admin(`*`),admin"
        self.grant_role(role=role)
        _,content,_ = self.retrieve_users()
        content = json.loads(content)
        found_query_select = False
        found_bucket_admin = False
        found_admin = False
        found = False
        for assignment in content:
            if assignment['id'] == user:
                for item in assignment['roles']:
                    if item['role'] == 'query_select':
                        found_query_select = True
                    if item['role'] == 'bucket_admin':
                        found_bucket_admin = True
                    if item['role'] == 'admin':
                        found_admin = True
        found = found_query_select & found_bucket_admin & found_admin
        self.assertTrue(found, "{0} not granted role {1} as expected".format(user, role))
        self.log.info("{0} granted role {1} as expected".format(user, role))

    def test_multiple_user_roles_precedence(self):
        self.create_users()
        self.shell.execute_command("killall cbq-engine")
        shell = RemoteMachineShellConnection(self.master)
        role = "query_select(default),views_admin(`*`),admin"
        self.grant_role(role=role)
        old_name = "employee-14"
        new_name = "employee-14-2"
        cmd = "curl -u {0}:{1} http://{2}:8093/query/service -d " \
              "'statement=UPDATE {3} a set name = '{4}' where name = '{5}' limit 1'".\
                format(self.users[0]['id'], self.users[0]['password'], self.master.ip, self.buckets[0].name, new_name, old_name)
        output, error = shell.execute_command(cmd)
        shell.log_command_output(output, error)
        self.assertTrue(any("success" in line for line in output), "Unable to update from {0} as user {1}".
                        format(self.buckets[0].name, self.users[0]['id']))
        self.log.info("Query executed successfully")

    def test_incorrect_n1ql_role(self):
        self.create_users()
        self.shell.execute_command("killall cbq-engine")
        self.grant_role()
        shell = RemoteMachineShellConnection(self.master)
        old_name = "employee-14"
        new_name = "employee-14-2"
        cmd = "curl -u {0}:{1} http://{2}:8093/query/service -d " \
              "'statement=UPDATE {3} a set name = '{4}' where name = '{5}' limit 1'".\
                format(self.users[0]['id'], self.users[0]['password'], self.master.ip, self.buckets[0].name, new_name, old_name)
        output, error = shell.execute_command(cmd)
        shell.log_command_output(output, error)
        self.assertTrue(any("User does not have credentials to access privilege cluster.bucket[default].n1ql.update!execute. "
                            "Add role Query Update [default] to allow the query to run." in line for line in output), "Able to update from {0} as user {1} - not expected behaviour".
                        format(self.buckets[0].name, self.users[0]['id']))
        self.log.info("Query failed as expected")

    def test_grant_incorrect_user(self):
        role = self.roles[0]['roles']
        self.query = "GRANT ROLE {0} to {1}".format(role, 'abc')
        try:
            self.run_cbq_query()
        except Exception as ex:
            self.log.info(str(ex))
            self.assertTrue("Unable to find user abc." in str(ex), "Able to grant role {0} to incorrect user abc - not expected".
                                                                format(role))
            self.log.info("Unable to grant role to incorrect user as expected")

    def test_grant_incorrect_role(self):
        user = self.users[0]['id']
        self.query = "GRANT ROLE {0} to {1}".format('abc', user)
        try:
            self.run_cbq_query()
        except Exception as ex:
            self.log.info(str(ex))
            self.assertTrue("Role abc is not valid." in str(ex), "Able to grant invalid role abc to {0} - not expected".
                                                                format(self.users[0]['id']))
            self.log.info("Unable to grant incorrect role to user as expected")

    def test_insert_nested_with_select_with_full_access(self):
        self.create_users()
        self.shell.execute_command("killall cbq-engine")
        self.grant_role()
        self.grant_role(role="query_select(default)")
        shell = RemoteMachineShellConnection(self.master)
        cmd = "curl -u %s:%s http://%s:8093/query/service -d " \
              "'statement=INSERT INTO %s (KEY UUID(), VALUE _name)" \
              " SELECT _name FROM %s _name WHERE age > 10'"%\
                (self.users[0]['id'], self.users[0]['password'], self.master.ip, self.buckets[0].name, self.buckets[0].name)
        output, error = shell.execute_command(cmd)
        shell.log_command_output(output, error)
        self.assertTrue(any("success" in line for line in output), "Unable to insert into {0} as user {1}".
                        format(self.buckets[0].name, self.users[0]['id']))
        self.log.info("Query executed successfully")

    def test_upsert_nested_with_select_with_full_access(self):
        self.create_users()
        self.shell.execute_command("killall cbq-engine")
        self.grant_role()
        self.grant_role(role="query_select(default)")
        shell = RemoteMachineShellConnection(self.master)
        cmd = "curl -u %s:%s http://%s:8093/query/service -d " \
              "'statement=UPSERT INTO %s (KEY UUID(), VALUE _name)" \
              " SELECT _name FROM %s _name WHERE age > 10'"%\
                (self.users[0]['id'], self.users[0]['password'], self.master.ip, self.buckets[0].name, self.buckets[0].name)
        output, error = shell.execute_command(cmd)
        shell.log_command_output(output, error)
        self.assertTrue(any("success" in line for line in output), "Unable to upsert into {0} as user {1}".
                        format(self.buckets[0].name, self.users[0]['id']))
        self.log.info("Query executed successfully")

    def test_update_nested_with_select_with_full_access(self):
        self.create_users()
        self.shell.execute_command("killall cbq-engine")
        self.grant_role()
        self.grant_role(role="query_select(default)")
        shell = RemoteMachineShellConnection(self.master)
        new_name = "employee-14-2"
        cmd = "curl -u {0}:{1} http://{2}:8093/query/service -d " \
              "'statement=UPDATE {3} a set name = '{4}' WHERE name IN (SELECT name FROM {5} WHERE age > 10)'".\
                format(self.users[0]['id'], self.users[0]['password'], self.master.ip, self.buckets[0].name, new_name, self.buckets[0].name)
        output, error = shell.execute_command(cmd)
        shell.log_command_output(output, error)
        self.assertTrue(any("success" in line for line in output), "Unable to update from {0} as user {1}".
                        format(self.buckets[0].name, self.users[0]['id']))
        self.log.info("Query executed successfully")

    def test_delete_nested_with_select_with_full_access(self):
        self.create_users()
        self.shell.execute_command("killall cbq-engine")
        self.grant_role()
        self.grant_role(role="query_select(default)")
        shell = RemoteMachineShellConnection(self.master)
        cmd = "curl -u {0}:{1} http://{2}:8093/query/service -d " \
              "'statement=DELETE FROM {3} a WHERE name IN (SELECT name FROM {4} WHERE age > 10)'".\
                format(self.users[0]['id'], self.users[0]['password'], self.master.ip, self.buckets[0].name, self.buckets[0].name)
        output, error = shell.execute_command(cmd)
        shell.log_command_output(output, error)
        self.assertTrue(any("success" in line for line in output), "Unable to delete from {0} as user {1}".
                        format(self.buckets[0].name, self.users[0]['id']))
        self.log.info("Query executed successfully")

    def test_insert_nested_with_select_with_no_access(self):
        self.create_users()
        self.shell.execute_command("killall cbq-engine")
        self.grant_role()
        shell = RemoteMachineShellConnection(self.master)
        cmd = "curl -u %s:%s http://%s:8093/query/service -d " \
              "'statement=INSERT INTO %s (KEY UUID(), VALUE _name)" \
              " SELECT _name FROM %s _name WHERE age > 10'"%\
                (self.users[0]['id'], self.users[0]['password'], self.master.ip, self.buckets[0].name, self.buckets[0].name)
        output, error = shell.execute_command(cmd)
        shell.log_command_output(output, error)
        self.assertTrue(any("User does not have credentials to access privilege cluster.bucket[default].n1ql.select!execute. "
                            "Add role Query Select [default] to allow the query to run." in line for line in output),
                            "Able to insert into {0} as user {1} - not expected".
                            format(self.buckets[0].name, self.users[0]['id']))
        self.log.info("Query failed as expected")

    def test_upsert_nested_with_select_with_no_access(self):
        self.create_users()
        self.shell.execute_command("killall cbq-engine")
        self.grant_role()
        shell = RemoteMachineShellConnection(self.master)
        cmd = "curl -u %s:%s http://%s:8093/query/service -d " \
              "'statement=UPSERT INTO %s (KEY UUID(), VALUE _name)" \
              " SELECT _name FROM %s _name WHERE age > 10'"%\
                (self.users[0]['id'], self.users[0]['password'], self.master.ip, self.buckets[0].name, self.buckets[0].name)
        output, error = shell.execute_command(cmd)
        shell.log_command_output(output, error)
        self.assertTrue(any("User does not have credentials to access privilege cluster.bucket[default].n1ql.select!execute. "
                            "Add role Query Select [default] to allow the query to run." in line for line in output),
                            "Able to upsert into {0} as user {1} - not expected".
                            format(self.buckets[0].name, self.users[0]['id']))
        self.log.info("Query failed as expected")

    def test_update_nested_with_select_with_no_access(self):
        self.create_users()
        self.shell.execute_command("killall cbq-engine")
        self.grant_role()
        shell = RemoteMachineShellConnection(self.master)
        new_name = "employee-14-2"
        cmd = "curl -u {0}:{1} http://{2}:8093/query/service -d " \
              "'statement=UPDATE {3} a set name = '{4}' WHERE name IN (SELECT name FROM {5} WHERE age > 10)'".\
                format(self.users[0]['id'], self.users[0]['password'], self.master.ip, self.buckets[0].name, new_name, self.buckets[0].name)
        output, error = shell.execute_command(cmd)
        shell.log_command_output(output, error)
        self.assertTrue(any("User does not have credentials to access privilege cluster.bucket[default].n1ql.select!execute. "
                            "Add role Query Select [default] to allow the query to run." in line for line in output),
                            "Able to update {0} as user {1} - not expected".
                            format(self.buckets[0].name, self.users[0]['id']))
        self.log.info("Query failed as expected")

    def test_delete_nested_with_select_with_no_access(self):
        self.create_users()
        self.shell.execute_command("killall cbq-engine")
        self.grant_role()
        shell = RemoteMachineShellConnection(self.master)
        cmd = "curl -u {0}:{1} http://{2}:8093/query/service -d " \
              "'statement=DELETE FROM {3} a WHERE name IN (SELECT name FROM {4} WHERE age > 10)'".\
                format(self.users[0]['id'], self.users[0]['password'], self.master.ip, self.buckets[0].name, self.buckets[0].name)
        output, error = shell.execute_command(cmd)
        shell.log_command_output(output, error)
        self.assertTrue(any("User does not have credentials to access privilege cluster.bucket[default].n1ql.select!execute. "
                            "Add role Query Select [default] to allow the query to run." in line for line in output),
                            "Able to insert into {0} as user {1} - not expected".
                            format(self.buckets[0].name, self.users[0]['id']))
        self.log.info("Query failed as expected")

    def test_insert_nested_with_select_with_full_access_and_diff_buckets(self):
        self.create_users()
        self.shell.execute_command("killall cbq-engine")
        self.grant_role()
        self.grant_role(role="query_select(bucket0)")
        shell = RemoteMachineShellConnection(self.master)
        cmd = "curl -u %s:%s http://%s:8093/query/service -d " \
              "'statement=INSERT INTO %s (KEY UUID(), VALUE _name)" \
              " SELECT _name FROM %s _name WHERE age > 10'"%\
                (self.users[0]['id'], self.users[0]['password'], self.master.ip, self.buckets[1].name, self.buckets[0].name)
        output, error = shell.execute_command(cmd)
        shell.log_command_output(output, error)
        self.assertTrue(any("success" in line for line in output), "Unable to insert into {0} and select from {1} as user {2}".
                        format(self.buckets[1].name, self.buckets[0].name, self.users[0]['id']))
        self.log.info("Query executed successfully")

    def test_insert_nested_with_select_with_no_access_and_diff_buckets(self):
        self.create_users()
        self.shell.execute_command("killall cbq-engine")
        self.grant_role()
        shell = RemoteMachineShellConnection(self.master)
        cmd = "curl -u %s:%s http://%s:8093/query/service -d " \
              "'statement=INSERT INTO %s (KEY UUID(), VALUE _name)" \
              " SELECT _name FROM %s _name WHERE age > 10'"%\
                (self.users[0]['id'], self.users[0]['password'], self.master.ip, self.buckets[1].name, self.buckets[0].name)
        output, error = shell.execute_command(cmd)
        shell.log_command_output(output, error)
        self.assertTrue(any("User does not have credentials to access privilege cluster.bucket[bucket0].n1ql.select!execute. "
                            "Add role Query Select [bucket0] to allow the query to run." in line for line in output),
                            "Able to select from {0} as user {1} - not expected".
                            format(self.buckets[1].name, self.users[0]['id']))
        self.log.info("Query failed as expected")

    def test_upsert_nested_with_select_with_full_access_with_diff_buckets(self):
        self.create_users()
        self.shell.execute_command("killall cbq-engine")
        self.grant_role()
        self.grant_role(role="query_select(bucket0)")
        shell = RemoteMachineShellConnection(self.master)
        cmd = "curl -u %s:%s http://%s:8093/query/service -d " \
              "'statement=UPSERT INTO %s (KEY UUID(), VALUE _name)" \
              " SELECT _name FROM %s _name WHERE age > 10'"%\
                (self.users[0]['id'], self.users[0]['password'], self.master.ip, self.buckets[1].name, self.buckets[0].name)
        output, error = shell.execute_command(cmd)
        shell.log_command_output(output, error)
        self.assertTrue(any("success" in line for line in output), "Unable to upsert into {0} and select from {1} as user {2}".
                        format(self.buckets[1].name, self.buckets[0].name, self.users[0]['id']))
        self.log.info("Query executed successfully")

    def test_upsert_nested_with_select_with_no_access_and_diff_buckets(self):
        self.create_users()
        self.shell.execute_command("killall cbq-engine")
        self.grant_role()
        shell = RemoteMachineShellConnection(self.master)
        cmd = "curl -u %s:%s http://%s:8093/query/service -d " \
              "'statement=UPSERT INTO %s (KEY UUID(), VALUE _name)" \
              " SELECT _name FROM %s _name WHERE age > 10'"%\
                (self.users[0]['id'], self.users[0]['password'], self.master.ip, self.buckets[1].name, self.buckets[0].name)
        output, error = shell.execute_command(cmd)
        shell.log_command_output(output, error)
        self.assertTrue(any("User does not have credentials to access privilege cluster.bucket[bucket0].n1ql.select!execute. "
                            "Add role Query Select [bucket0] to allow the query to run." in line for line in output),
                            "Able to select from {0} as user {1} - not expected".
                            format(self.buckets[1].name, self.users[0]['id']))
        self.log.info("Query failed as expected")

    def test_update_nested_with_select_with_full_access_and_diff_buckets(self):
        self.create_users()
        self.shell.execute_command("killall cbq-engine")
        self.grant_role()
        self.grant_role(role="query_select(bucket0)")
        shell = RemoteMachineShellConnection(self.master)
        new_name = "employee-14-2"
        cmd = "curl -u {0}:{1} http://{2}:8093/query/service -d " \
              "'statement=UPDATE {3} a set name = '{4}' WHERE name IN (SELECT name FROM {5} WHERE age > 10)'".\
                format(self.users[0]['id'], self.users[0]['password'], self.master.ip, self.buckets[1].name, new_name, self.buckets[0].name)
        output, error = shell.execute_command(cmd)
        shell.log_command_output(output, error)
        self.assertTrue(any("success" in line for line in output), "Unable to update {0} and select from {1} as user {2}".
                        format(self.buckets[1].name, self.buckets[0].name, self.users[0]['id']))
        self.log.info("Query executed successfully")

    def test_update_nested_with_select_with_no_access_and_diff_buckets(self):
        self.create_users()
        self.shell.execute_command("killall cbq-engine")
        self.grant_role()
        shell = RemoteMachineShellConnection(self.master)
        new_name = "employee-14-2"
        cmd = "curl -u {0}:{1} http://{2}:8093/query/service -d " \
              "'statement=UPDATE {3} a set name = '{4}' WHERE name IN (SELECT name FROM {5} WHERE age > 10)'".\
                format(self.users[0]['id'], self.users[0]['password'], self.master.ip, self.buckets[1].name, new_name, self.buckets[0].name)
        output, error = shell.execute_command(cmd)
        shell.log_command_output(output, error)
        self.assertTrue(any("User does not have credentials to access privilege cluster.bucket[bucket0].n1ql.select!execute. "
                            "Add role Query Select [bucket0] to allow the query to run." in line for line in output),
                            "Able to select from {0} as user {1} - not expected".
                            format(self.buckets[1].name, self.users[0]['id']))
        self.log.info("Query failed as expected")

    def test_delete_nested_with_select_with_full_access_and_diff_buckets(self):
        self.create_users()
        self.shell.execute_command("killall cbq-engine")
        self.grant_role()
        self.grant_role(role="query_select(default)")
        shell = RemoteMachineShellConnection(self.master)
        cmd = "curl -u {0}:{1} http://{2}:8093/query/service -d " \
              "'statement=DELETE FROM {3} a WHERE name IN (SELECT name FROM {4} WHERE age > 10)'".\
                format(self.users[0]['id'], self.users[0]['password'], self.master.ip, self.buckets[1].name, self.buckets[0].name)
        output, error = shell.execute_command(cmd)
        shell.log_command_output(output, error)
        self.assertTrue(any("success" in line for line in output), "Unable to delete from {0} and select from {1} as user {2}".
                        format(self.buckets[1].name, self.buckets[0].name, self.users[0]['id']))
        self.log.info("Query executed successfully")

    def test_delete_nested_with_select_with_no_access_and_diff_buckets(self):
        self.create_users()
        self.shell.execute_command("killall cbq-engine")
        self.grant_role()
        shell = RemoteMachineShellConnection(self.master)
        cmd = "curl -u {0}:{1} http://{2}:8093/query/service -d " \
              "'statement=DELETE FROM {3} a WHERE name IN (SELECT name FROM {4} WHERE age > 10)'".\
                format(self.users[0]['id'], self.users[0]['password'], self.master.ip, self.buckets[1].name, self.buckets[0].name)
        output, error = shell.execute_command(cmd)
        shell.log_command_output(output, error)
        self.assertTrue(any("User does not have credentials to access privilege cluster.bucket[bucket0].n1ql.select!execute. "
                            "Add role Query Select [bucket0] to allow the query to run." in line for line in output),
                            "Able to select from {0} as user {1} - not expected".
                            format(self.buckets[1].name, self.users[0]['id']))
        self.log.info("Query failed as expected")