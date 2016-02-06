import json
import time
from threading import Thread, Event
from basetestcase import BaseTestCase
from couchbase_helper.document import DesignDocument, View
from couchbase_helper.documentgenerator import DocumentGenerator
from membase.api.rest_client import RestConnection
from membase.helper.rebalance_helper import RebalanceHelper
from membase.api.exception import ReadDocumentException
from membase.api.exception import DesignDocCreationException
from membase.helper.cluster_helper import ClusterOperationHelper
from remote.remote_util import RemoteMachineShellConnection
from random import randint
from datetime import datetime
import time
import commands
import logger
import ssl
import httplib2
import httplib
import urllib
import socket
import base64
import paramiko
import requests

log = logger.Logger.get_logger()

class ServerInfo():
    def __init__(self,
                 ip,
                 port,
                 ssh_username,
                 ssh_password,
                 ssh_key=''):

        self.ip = ip
        self.ssh_username = ssh_username
        self.ssh_password = ssh_password
        self.port = port
        self.ssh_key = ssh_key


class x509main:
    CHAINCERTFILE = 'chain.pem'
    NODECAKEYFILE = 'pkey.pem'
    CACERTFILE = "root.crt"
    CAKEYFILE = "root.key"
    WININSTALLPATH = "C:/Program Files/Couchbase/Server/var/lib/couchbase/"
    LININSTALLPATH = "/opt/couchbase/var/lib/couchbase/"
    MACINSTALLPATH = "/Users/couchbase/Library/Application Support/Couchbase/var/lib/couchbase/"
    DOWNLOADPATH = "/tmp/"
    CACERTFILEPATH = "/tmp/newcerts/"
    CHAINFILEPATH = "inbox"
    GOCERTGENFILE = "gencert.go"
    INCORRECT_ROOT_CERT = "incorrect_root_cert.crt"

    def __init__(self,
                 host=None,
                 method='REST'):

        print host
        if host is not None:
            self.host = host
            self.install_path = self._get_install_path(self.host)
        self.slave_host = ServerInfo('127.0.0.1', 22, 'root', 'couchbase')

    def getLocalIPAddress(self):

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('couchbase.com', 0))
        return s.getsockname()[0]
        '''
        status, ipAddress = commands.getstatusoutput("ifconfig en0 | grep 'inet addr:' | cut -d: -f2 |awk '{print $1}'")
        if '1' not in ipAddress:
            status, ipAddress = commands.getstatusoutput("ifconfig eth0 | grep  -Eo 'inet (addr:)?([0-9]*\.){3}[0-9]*' | awk '{print $2}'")
        return ipAddress
        '''

    def setup_cluster_nodes_ssl(self,servers=[],reload_cert=False):
        for server in servers:
            x509main(server)._setup_node_certificates(reload_cert=reload_cert)

    def _generate_cert(self,servers,root_cn='Root\ Authority'):
        files = []
        cert_file = "./pytests/security/" + x509main.GOCERTGENFILE
        shell = RemoteMachineShellConnection(self.slave_host)
        shell.execute_command("rm -rf /tmp/newcerts")
        shell.execute_command("mkdir /tmp/newcerts")

        shell.execute_command("go run " + cert_file + " -store-to=/tmp/newcerts/root -common-name="+root_cn)
        shell.execute_command("go run " + cert_file + " -store-to=/tmp/newcerts/interm -sign-with=/tmp/newcerts/root -common-name=Intemediate\ Authority")
        for server in servers:
            shell.execute_command("go run " + cert_file + " -store-to=/tmp/newcerts/" + server.ip + " -sign-with=/tmp/newcerts/interm -common-name=" + server.ip + " -final=true")
            shell.execute_command("cat /tmp/newcerts/" + server.ip + ".crt /tmp/newcerts/interm.crt  > " + " /tmp/newcerts/long_chain"+server.ip+".pem")

        shell.execute_command("go run " + cert_file + " -store-to=/tmp/newcerts/incorrect_root_cert -common-name=Incorrect\ Authority")

    def _reload_node_certificate(self,host):
        rest = RestConnection(host)
        api = rest.baseUrl + "node/controller/reloadCertificate"
        status, content, header = rest._http_request(api, 'POST')
        return status, content, header

    def _get_install_path(self,host):
        shell = RemoteMachineShellConnection(host)
        os_type = shell.extract_remote_info().distribution_type
        log.info ("OS type is {0}".format(os_type))
        if os_type == 'windows':
            install_path = x509main.WININSTALLPATH
        elif os_type == 'Mac':
            install_path = x509main.MACINSTALLPATH
        else:
            install_path = x509main.LININSTALLPATH

        return install_path

    def _create_inbox_folder(self,host):
        shell = RemoteMachineShellConnection(self.host)
        final_path = self.install_path + x509main.CHAINFILEPATH
        shell.execute_command('mkdir ' + final_path)


    def _delete_inbox_folder(self):
        shell = RemoteMachineShellConnection(self.host)
        final_path = self.install_path + x509main.CHAINFILEPATH
        shell.execute_command('rm -rf ' + final_path)

    def _copy_node_key_chain_cert(self,host,src_path,dest_path):
        shell = RemoteMachineShellConnection(host)
        shell.copy_file_local_to_remote(src_path,dest_path)

    def _setup_node_certificates(self,chain_cert=True,node_key=True,reload_cert=True):
        self._create_inbox_folder(self.host)
        src_chain_file = "/tmp/newcerts/long_chain" + self.host.ip + ".pem"
        dest_chain_file = self.install_path + x509main.CHAINFILEPATH + "/" + x509main.CHAINCERTFILE
        src_node_key = "/tmp/newcerts/" + self.host.ip + ".key"
        dest_node_key = self.install_path + x509main.CHAINFILEPATH + "/" + x509main.NODECAKEYFILE
        if chain_cert:
            self._copy_node_key_chain_cert(self.host, src_chain_file, dest_chain_file)
        if node_key:
            self._copy_node_key_chain_cert(self.host, src_node_key, dest_node_key)
        if reload_cert:
            status, content, header = self._reload_node_certificate(self.host)
            print status
            print content
            print header
            return status, content, header


    def _create_rest_headers(self,username="Administrator",password="password"):
        authorization = base64.encodestring('%s:%s' % (username,password))
        return {'Content-Type': 'application/octet-stream',
            'Authorization': 'Basic %s' % authorization,
            'Accept': '*/*'}


    def _rest_upload_file(self,URL,file_path_name,username=None,password=None):
        data  =  open(file_path_name, 'rb').read()
        http = httplib2.Http()
        status, content = http.request(URL, 'POST', headers=self._create_rest_headers(username,password),body=data)
        print URL
        print status
        print content
        return status, content


    def _upload_cluster_ca_certificate(self,username,password):
        rest = RestConnection(self.host)
        url = "controller/uploadClusterCA"
        api = rest.baseUrl + url
        self._rest_upload_file(api,"/tmp/newcerts/" + x509main.CACERTFILE,"Administrator",'password')


    def _validate_ssl_login(self,host=None,port=18091,username='Administrator',password='password'):
        key_file = x509main.CACERTFILEPATH + x509main.CAKEYFILE
        cert_file = x509main.CACERTFILEPATH + x509main.CACERTFILE
        if host is None:
            host = self.host.ip
        try:
            r = requests.get("https://"+host+":18091",verify=cert_file)
            if r.status_code == 200:
                header = {'Content-type': 'application/x-www-form-urlencoded'}
                params = urllib.urlencode({'user':'{0}'.format(username), 'password':'{0}'.format(password)})
                r = requests.post("https://"+host+":18091/uilogin",data=params,headers=header,verify=cert_file)
                return r.status_code
        except Exception, ex:
            print "into exception"
            print ex
            return 'error'

    def _get_cluster_ca_cert(self):
        rest = RestConnection(self.host)
        api = rest.baseUrl + "pools/default/certificate?extended=true"
        status, content, header = rest._http_request(api, 'GET')
        return status, content, header

    def setup_master(self,user='Administrator',password='password'):
        x509main(self.host)._upload_cluster_ca_certificate(user,password)
        x509main(self.host)._setup_node_certificates()
