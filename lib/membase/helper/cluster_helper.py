from membase.api.rest_client import RestConnection, RestHelper
import logger
import testconstants

class ClusterOperationHelper(object):
    #the first ip is taken as the master ip

    @staticmethod
    def add_and_rebalance(servers,rest_password):
        log = logger.Logger.get_logger()
        master = servers[0]
        all_nodes_added = True
        rebalanced = True
        rest = RestConnection(master)
        if len(servers) > 1:
            for serverInfo in servers[1:]:
                log.info('adding node : {0} to the cluster'.format(serverInfo.ip))
                otpNode = rest.add_node("Administrator", rest_password, serverInfo.ip, port=serverInfo.port)
                if otpNode:
                    log.info('added node : {0} to the cluster'.format(otpNode.id))
                else:
                    all_nodes_added = False
                    break
            if all_nodes_added:
                rest.rebalance(otpNodes=[node.id for node in rest.node_statuses()], ejectedNodes=[])
                rebalanced &= rest.monitorRebalance()
        return all_nodes_added and rebalanced

    @staticmethod
    def add_all_nodes_or_assert(master,all_servers,rest_settings,test_case):
        log = logger.Logger.get_logger()
        otpNodes = []
        all_nodes_added = True
        rest = RestConnection(master)
        for serverInfo in all_servers:
            if serverInfo.ip != master.ip:
                log.info('adding node : {0} to the cluster'.format(serverInfo.ip))
                otpNode = rest.add_node(rest_settings.rest_username,
                                        rest_settings.rest_password,
                                        serverInfo.ip)
                if otpNode:
                    log.info('added node : {0} to the cluster'.format(otpNode.id))
                    otpNodes.append(otpNode)
                else:
                    all_nodes_added = False
        if not all_nodes_added:
            if test_case:
                test_case.assertTrue(all_nodes_added,
                                     msg="unable to add all the nodes to the cluster")
            else:
                log.error("unable to add all the nodes to the cluster")
        return otpNodes

    @staticmethod
    def wait_for_ns_servers_or_assert(servers,testcase):
        for server in servers:
            rest = RestConnection(server)
            log = logger.Logger.get_logger()
            log.info("waiting for ns_server @ {0}:{1}".format(server.ip, server.port))
            testcase.assertTrue(RestHelper(rest).is_ns_server_running(),
                            "ns_server is not running in {0}".format(server.ip))

    @staticmethod
    def cleanup_cluster(servers):
        log = logger.Logger.get_logger()
        rest = RestConnection(servers[0])
        RestHelper(rest).is_ns_server_running(timeout_in_seconds=testconstants.NS_SERVER_TIMEOUT)
        nodes = rest.node_statuses()
        master_id = rest.get_nodes_self().id
        if len(nodes) > 1:
                log.info("rebalancing all nodes in order to remove nodes")
                helper = RestHelper(rest)
                removed = helper.remove_nodes(knownNodes=[node.id for node in nodes],
                                              ejectedNodes=[node.id for node in nodes if node.id != master_id])
                log.info("removed all the nodes from cluster associated with {0} ? {1}".format(servers[0], removed))