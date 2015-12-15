import os
import shutil

from basetestcase import BaseTestCase
from ent_backup_restore.validation_helpers.backup_restore_validations import BackupRestoreValidations
from membase.helper.bucket_helper import BucketOperationHelper
from membase.helper.cluster_helper import ClusterOperationHelper
from remote.remote_util import RemoteMachineShellConnection


class EnterpriseBackupRestoreBase(BaseTestCase):
    def setUp(self):
        super(EnterpriseBackupRestoreBase, self).setUp()
        self.backupset = Backupset()
        self.backupset.backup_host = self.input.clusters[1][0]
        self.backupset.directory = self.input.param("dir", "/tmp/entbackup")
        self.backupset.name = self.input.param("name", "backup")
        self.backupset.cluster_host = self.servers[0]
        self.backupset.cluster_host_username = self.servers[0].rest_username
        self.backupset.cluster_host_password = self.servers[0].rest_password
        self.same_cluster = self.input.param("same-cluster", True)
        if self.same_cluster:
            self.backupset.restore_cluster_host = self.servers[0]
            self.backupset.restore_cluster_host_username = self.servers[0].rest_username
            self.backupset.restore_cluster_host_password = self.servers[0].rest_password
        else:
            self.backupset.restore_cluster_host = self.input.clusters[0][0]
            self.backupset.restore_cluster_host_username = self.input.clusters[0][0].rest_username
            self.backupset.restore_cluster_host_password = self.input.clusters[0][0].rest_password
        self.backupset.exclude_buckets = self.input.param("exclude-buckets", "")
        self.backupset.include_buckets = self.input.param("include-buckets", "")
        self.backupset.disable_bucket_config = self.input.param("disable-bucket-config", False)
        self.backupset.disable_views = self.input.param("disable-views", False)
        self.backupset.disable_gsi_indexes = self.input.param("disable-gsi-indexes", False)
        self.backupset.disable_ft_indexes = self.input.param("disable-ft-indexes", False)
        self.backupset.disable_data = self.input.param("disable-data", False)
        self.backupset.resume = self.input.param("resume", False)
        self.backupset.purge = self.input.param("purge", False)
        self.backupset.threads = self.input.param("threads", self.number_of_processors())
        self.backupset.start = self.input.param("start", 1)
        self.backupset.end = self.input.param("stop", 1)
        self.backupset.number_of_backups = self.input.param("number_of_backups", 1)
        self.backupset.filter_keys = self.input.param("filter-keys", "")
        self.backupset.filter_values = self.input.param("filter-values", "")
        self.backupset.backup_list_name = self.input.param("list-names", None)
        self.backupset.backup_incr_backup = self.input.param("incr-backup", None)
        self.backupset.bucket_backup = self.input.param("bucket-backup", None)
        self.backupset.backup_to_compact = self.input.param("backup-to-compact", 0)
        self.cli_command_location = "/opt/couchbase/bin"
        self.backups = []
        self.backup_validation_files_location = "/tmp/backuprestore"
        self.validation_helper = BackupRestoreValidations(self.backupset, self.cluster_to_backup, self.cluster_to_restore,
                                                          self.buckets, self.backup_validation_files_location)
        self.number_of_backups_taken = 0
        self.vbucket_seqno = []
        if not os.path.exists(self.backup_validation_files_location):
            os.mkdir(self.backup_validation_files_location)

    def tearDown(self):
        super(EnterpriseBackupRestoreBase, self).tearDown()
        remote_client = RemoteMachineShellConnection(self.input.clusters[1][0])
        command = "rm -rf {0}".format(self.input.param("dir", "/tmp/entbackup"))
        output, error = remote_client.execute_command(command)
        remote_client.log_command_output(output, error)
        if self.input.clusters and not self.input.param("skip_cleanup", False):
            for key in self.input.clusters.keys():
                servers = self.input.clusters[key]
                self.backup_reset_clusters(servers)
        if os.path.exists("/tmp/backuprestore"):
            shutil.rmtree("/tmp/backuprestore")

    @property
    def cluster_to_backup(self):
        return self.get_nodes_in_cluster(self.backupset.cluster_host)

    @property
    def cluster_to_restore(self):
        return self.get_nodes_in_cluster(self.backupset.restore_cluster_host)

    def number_of_processors(self):
        remote_client = RemoteMachineShellConnection(self.input.clusters[1][0])
        command = "nproc"
        output, error = remote_client.execute_command(command)
        if output:
            return output[0]
        else:
            return error[0]

    def backup_reset_clusters(self, servers):
        BucketOperationHelper.delete_all_buckets_or_assert(servers, self)
        ClusterOperationHelper.cleanup_cluster(servers, master=servers[0])
        ClusterOperationHelper.wait_for_ns_servers_or_assert(servers, self)

    def store_vbucket_seqno(self):
        vseqno = self.get_vbucket_seqnos(self.cluster_to_backup, self.buckets)
        self.vbucket_seqno.append(vseqno)

    def backup_create(self):
        args = "create --dir {0} --name {1}".format(self.backupset.directory, self.backupset.name)
        if self.backupset.exclude_buckets:
            args += " --exclude-buckets \"{0}\"".format(",".join(self.backupset.exclude_buckets))
        if self.backupset.include_buckets:
            args += " --include-buckets=\"{0}\"".format(",".join(self.backupset.include_buckets))
        if self.backupset.disable_bucket_config:
            args += " --disable-bucket-config"
        if self.backupset.disable_views:
            args += " --disable-views"
        if self.backupset.disable_gsi_indexes:
            args += " --disable-gsi-indexes"
        if self.backupset.disable_ft_indexes:
            args += " --disable-ft-indexes"
        if self.backupset.disable_data:
            args += " --disable-data"
        remote_client = RemoteMachineShellConnection(self.backupset.backup_host)
        command = "{0}/backup {1}".format(self.cli_command_location, args)
        output, error = remote_client.execute_command(command)
        remote_client.log_command_output(output, error)
        return output, error

    def backup_create_validate(self):
        output, error = self.backup_create()
        if error or "Backup `{0}` created successfully".format(self.backupset.name) not in output:
            self.fail("Creating backupset failed.")
        status, msg = self.validation_helper.validate_backup_create()
        if not status:
            self.fail(msg)
        self.log.info(msg)

    def backup_cluster(self):
        args = "cluster --dir {0} --name {1} --host http://{2}:{3} --username {4} --password {5}". \
            format(self.backupset.directory, self.backupset.name, self.backupset.cluster_host.ip,
                   self.backupset.cluster_host.port, self.backupset.cluster_host_username,
                   self.backupset.cluster_host_password)
        if self.backupset.resume:
            args += "--resume"
        if self.backupset.purge:
            args += "--purge"
        remote_client = RemoteMachineShellConnection(self.backupset.backup_host)
        command = "{0}/backup {1}".format(self.cli_command_location, args)
        output, error = remote_client.execute_command(command)
        remote_client.log_command_output(output, error)
        if output:
            return output, error
        command = "ls -tr {0}/{1} | tail -1".format(self.backupset.directory, self.backupset.name)
        o, e = remote_client.execute_command(command)
        if o:
            self.backups.append(o[0])
        self.number_of_backups_taken += 1
        self.log.info("Finished taking backup  with args: {0}".format(args))
        return output, error

    def backup_cluster_validate(self):
        output, error = self.backup_cluster()
        if output:
            self.fail("Taking cluster backup failed.")
        #status, msg = self.validation_helper.validate_backup()
        #if not status:
        #    self.fail(msg)
        #self.log.info(msg)
        self.store_vbucket_seqno()
        self.validation_helper.store_keys(self.cluster_to_backup, self.buckets, self.number_of_backups_taken,
                                          self.backup_validation_files_location)
        self.validation_helper.store_latest(self.cluster_to_backup, self.buckets, self.number_of_backups_taken,
                                            self.backup_validation_files_location)

    def backup_restore(self):
        try:
            backup_start = self.backups[int(self.backupset.start) - 1]
        except IndexError:
            backup_start = "{0}{1}".format(self.backups[-1], self.backupset.start)
        try:
            backup_end = self.backups[int(self.backupset.end) - 1]
        except IndexError:
            backup_end = "{0}{1}".format(self.backups[-1], self.backupset.end)
        args = "restore --dir {0} --name {1} --host http://{2}:{3} --username {4} --password {5} --start {6} " \
               "--end {7} --force-updates".format(self.backupset.directory, self.backupset.name,
                                                  self.backupset.restore_cluster_host.ip,
                                                  self.backupset.restore_cluster_host.port,
                                                  self.backupset.restore_cluster_host_username,
                                                  self.backupset.restore_cluster_host_password, backup_start,
                                                  backup_end)
        if self.backupset.exclude_buckets:
            args += "--exclude-buckets".format(self.backupset.exclude_buckets)
        if self.backupset.include_buckets:
            args += "--include-buckets {0}".format(self.backupset.include_buckets)
        if self.backupset.disable_bucket_config:
            args += "--disable-bucket-config {0}".format(self.backupset.disable_bucket_config)
        if self.backupset.disable_views:
            args += "--disable-views {0}".format(self.backupset.disable_views)
        if self.backupset.disable_gsi_indexes:
            args += "--disable-gsi-indexes {0}".format(self.backupset.disable_gsi_indexes)
        if self.backupset.disable_ft_indexes:
            args += "--disable-ft-indexes {0}".format(self.backupset.disable_ft_indexes)
        if self.backupset.disable_data:
            args += "--disable-data {0}".format(self.backupset.disable_data)
        if self.backupset.filter_keys:
            args += "--filter_keys {0}".format(self.backupset.filter_keys)
        if self.backupset.filter_values:
            args += "--filter_values {0}".format(self.backupset.filter_values)
        remote_client = RemoteMachineShellConnection(self.backupset.backup_host)
        command = "{0}/backup {1}".format(self.cli_command_location, args)
        output, error = remote_client.execute_command(command)
        remote_client.log_command_output(output, error)
        return output, error

    def backup_restore_validate(self, compare_uuid=False, seqno_compare_function="==", replicas=False, mode="memory"):
        output, error = self.backup_restore()
        if "Transfer plan finished successfully" not in error[-1]:
            self.fail("Restoring backup failed.")
        self.log.info("Finished restoring backup")
        current_vseqno = self.get_vbucket_seqnos(self.cluster_to_restore, self.buckets)
        status, msg = self.validation_helper.validate_restore(self.backupset.end, self.vbucket_seqno, current_vseqno,
                                                              compare_uuid=compare_uuid, compare=seqno_compare_function,
                                                              get_replica=replicas, mode=mode)

        if not status:
            self.fail(msg)
        self.log.info(msg)

    def backup_list(self):
        args = "list --dir {0}".format(self.backupset.directory)
        if self.backupset.backup_list_name:
            args += "--name {0}".format(self.backupset.backup_list_name)
        if self.backupset.backup_incr_backup:
            args += "--incr-backup {0}".format(self.backupset.backup_incr_backup)
        if self.backupset.bucket_backup:
            args += "--bucket-backup {0}".format(self.backupset.bucket_backup)
        remote_client = RemoteMachineShellConnection(self.backupset.backup_host)
        command = "{0}/backup {1}".format(self.cli_command_location, args)
        output, error = remote_client.execute_command(command)
        remote_client.log_command_output(output, error)
        if error:
            return False, error, "Getting backup list failed."
        else:
            return True, output, "Backup list obtained"

    def backup_compact(self):
        try:
            backup_to_compact = self.buckets[int(self.backupset.backup_to_compact)]
        except IndexError:
            backup_to_compact = "{0}{1}".format(self.buckets[-1], self.backupset.backup_to_compact)
        args = "compact --dir {0} --name {1} --backup {2}".format(self.backupset.directory, self.backupset.name,
                                                                  backup_to_compact)
        remote_client = RemoteMachineShellConnection(self.backupset.backup_host)
        command = "{0}/backup {1}".format(self.cli_command_location, args)
        output, error = remote_client.execute_command(command)
        remote_client.log_command_output(output, error)
        if error:
            return False, error, "Compacting backup failed."
        else:
            return True, output, "Compaction of backup success"

    def backup_remove(self):
        args = "remove --dir {0} --name {1}".format(self.backupset.directory, self.backupset.name)
        remote_client = RemoteMachineShellConnection(self.backupset.backup_host)
        command = "{0}/backup {1}".format(self.cli_command_location, args)
        output, error = remote_client.execute_command(command)
        remote_client.log_command_output(output, error)
        self.verify_cluster_stats()
        if error:
            return False, error, "Removing backup failed."
        else:
            return True, output, "Removing of backup success"


class Backupset:
    def __init__(self):
        self.backup_host = None
        self.directory = ''
        self.name = ''
        self.cluster_host = None
        self.cluster_host_username = ''
        self.cluster_host_password = ''
        self.restore_cluster_host = None
        self.restore_cluster_host_username = ''
        self.restore_cluster_host_password = ''
        self.threads = ''
        self.exclude_buckets = []
        self.include_buckets = []
        self.disable_bucket_config = False
        self.disable_views = False
        self.disable_gsi_indexes = False
        self.disable_ft_indexes = False
        self.disable_data = False
        self.resume = False
        self.purge = False
        self.start = 1
        self.end = 1
        self.number_of_backups = 1
        self.filter_keys = ''
        self.filter_values = ''
        self.backup_list_name = ''
        self.backup_incr_backup = ''
        self.bucket_backup = ''
        self.backup_to_compact = ''
