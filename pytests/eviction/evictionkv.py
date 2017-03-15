import random
import time
import uuid

import mc_bin_client
from couchbase_helper.documentgenerator import BlobGenerator
from eviction.evictionbase import EvictionBase
from membase.api.rest_client import RestConnection
from memcached.helper.data_helper import MemcachedClientHelper
from sdk_client import SDKClient


class EvictionKV(EvictionBase):


    def verify_all_nodes(self):
        stats_tasks = []
        for s in self.servers:
            stats_tasks.append( self.cluster.async_wait_for_stats([s], "default", "",
                                    "curr_items", "==", 0) )

        for task in stats_tasks:
            task.result(60)

    def test_verify_expiry_via_compactor_cancelled_compact(self):

        self.load_set_to_be_evicted(20, 10000)
        self.log.info("sleeping {0} seconds to allow keys to be evicted".format(self.expires + 30 ))
        time.sleep(self.expires + 30)
        self.run_expiry_pager(60*60*24)   # effectively disable it by setting it far off in the future

        compacted = self.cluster.compact_bucket(self.master, 'default')
        self.assertTrue(compacted, msg="unable compact_bucket")

        self.cluster.cancel_bucket_compaction(self.master, 'default')

        # start compaction again
        time.sleep(5)
        compacted = self.cluster.compact_bucket(self.master, 'default')
        self.assertTrue(compacted, msg="unable compact_bucket")


        self.cluster.wait_for_stats([self.master],
                                    "default", "",
                                    "curr_items", "==", 0, timeout=30)


    def test_verify_expiry_via_compactor(self):



        self.run_expiry_pager(60*60*24*7)      # effectively disable it by setting it one week ahead
        self.load_set_to_be_evicted(self.expires, self.keys_count)

        self.log.info("sleeping {0} seconds to allow keys to be evicted".format(self.expires + 30 ))
        time.sleep(self.expires + 30 )   # 30 seconds grace period


        # run the compactor which should expire the kyes
        compacted = self.cluster.compact_bucket(self.master, 'default')

        self.verify_all_nodes()






    """
    add new keys at the same rate as keys are expiring
    Here is the algorithm:
      - initally set n keys to expire in chunk, the first chunk expiring after the keys are initially set - thus
        the init time delay value added to the expiry time - this may need to be adjusted
      - in each interval set the same number of keys as is expected to expire

    Note: this us implemented with compaction doing the eviction, in the future this could be enhanced to have
    the pager expiry doing the eviction.
    """

    def test_steady_state_eviction(self):
        serverInfo = self.master
        client = MemcachedClientHelper.direct_client(serverInfo, 'default')

        expiry_time = self.input.param("expiry_time", 30)
        keys_expired_per_interval = self.input.param("keys_expired_per_interval", 100)
        key_float = self.input.param("key_float", 1000)

        # we want to have keys expire after all the key are initialized, thus the below parameter
        init_time_delay = self.input.param("init_time_delay",30)
        test_time_in_minutes = self.input.param( "test_time_in_minutes",30)



        # rampup - create a certain number of keys
        float_creation_chunks = key_float / keys_expired_per_interval
        print 'float_creation_chunks', float_creation_chunks
        for i in range( float_creation_chunks):
            #print 'setting', keys_expired_per_interval, ' keys to expire in', expiry_time * (i+1)
            for j in range(keys_expired_per_interval):
               key = str(uuid.uuid4()) + str(i) + str(j)
               client.set(key, init_time_delay + expiry_time * (i+1), 0, key)


        for i in range(test_time_in_minutes * 60/expiry_time):


            key_set_time = int( time.time())

            # ClusterOperationHelper.set_expiry_pager_sleep_time(self.master, 'default')
            testuuid = uuid.uuid4()
            keys = ["key_%s_%d" % (testuuid, i) for i in range(keys_expired_per_interval)]
            self.log.info("pushing keys with expiry set to {0}".format(expiry_time))
            for key in keys:
                try:
                    client.set(key, expiry_time + key_float/expiry_time, 0, key)
                except mc_bin_client.MemcachedError as error:
                    msg = "unable to push key : {0} to bucket : {1} error : {2}"
                    self.log.error(msg.format(key, client.vbucketId, error.status))
                    self.fail(msg.format(key, client.vbucketId, error.status))
            self.log.info("inserted {0} keys with expiry set to {1}".format(len(keys), expiry_time))
            self.log.info('sleeping {0} seconds'.format(expiry_time - (time.time()- key_set_time) ) )


            # have the compactor do the expiry
            compacted = self.cluster.compact_bucket(self.master, 'default')

            self.cluster.wait_for_stats([self.master], "default", "", "curr_items", "==", key_float, timeout=30)
            time.sleep( expiry_time - (time.time()- key_set_time))





    def test_verify_expiry(self):
        """
            heavy dgm purges expired items via compactor.
            this is a smaller test to load items below compactor
            threshold and check if items still expire via pager
        """

        self.load_set_to_be_evicted(20, 100)
        self.run_expiry_pager()
        print "sleep 40 seconds and verify all items expired"
        time.sleep(40)
        self._verify_all_buckets(self.master)
        self.cluster.wait_for_stats([self.master],
                                    "default", "",
                                    "curr_items", "==", 0, timeout=60)


    def test_eject_all_ops(self):
        """
            eject all items and ensure items can still be retrieved, deleted, and udpated
            when fulleviction enabled
        """
        self.load_ejected_set(600)
        self.load_to_dgm()

        self.ops_on_ejected_set("read",   1,   200)
        self.ops_on_ejected_set("delete", 201, 400)
        self.ops_on_ejected_set("update", 401, 600)

    def test_purge_ejected_docs(self):
        """
           Go into dgm with expired items and verify at end of load no docs expired docs remain
           and ejected docs can still be deleted resulting in 0 docs left in cluster
        """
        num_ejected = 100
        ttl = 240

        self.load_ejected_set(num_ejected)
        self.load_to_dgm(ttl=ttl)


        while ttl > 0:
            self.log.info("%s seconds until loaded docs expire" % ttl)
            time.sleep(10)
            ttl = ttl - 10


        # compact to purge expiring docs
        compacted = self.cluster.compact_bucket(self.master, 'default')
        self.assertTrue(compacted, msg="unable compact_bucket")

        iseq = self.cluster.wait_for_stats([self.master],
                                           "default", "",
                                           "curr_items", "==", num_ejected, timeout=120)
        self.assertTrue(iseq, msg="curr_items != {0}".format(num_ejected))


        # delete remaining non expiring docs
        self.ops_on_ejected_set("delete", 0, num_ejected)
        iseq = self.cluster.wait_for_stats([self.master],
                                            "default", "",
                                            "curr_items", "==", 0, timeout=30)
        self.assertTrue(iseq, msg="curr_items != {0}".format(0))



    def test_update_ejected_expiry_time(self):
        """
            eject all items set to expire
        """

        self.load_ejected_set(100)
        self.load_to_dgm(ttl=30)
        self.ops_on_ejected_set("update", ttl=30)

        # run expiry pager
        self.run_expiry_pager()

        self.cluster.wait_for_stats([self.master],
                                    "default", "",
                                    "curr_items", "==", 0, timeout=30)


    # Ephemeral buckets tests start here


    # Ephemeral bucket configured with no eviction
    # 1. Configure an ephemeral bucket with no eviction
    # 2. Set kvs until we get OOM returned - this is expected
    # 3. Explicitly delete some KVs
    # 4. Add more kvs - should succeed
    # 5. Add keys until OOM is returned


    def test_ephemeral_bucket_no_eviction(self):

        generate_load = BlobGenerator(EvictionKV.KEY_ROOT, 'param2', self.value_size, start=0, end=self.num_items)
        self._load_all_ephemeral_buckets_until_no_more_memory(self.servers[0], generate_load, "create", 0, self.num_items)


        # figure out how many items were loaded and load 10% more
        rest = RestConnection(self.servers[0])
        itemCount = rest.get_bucket(self.buckets[0]).stats.itemCount

        self.log.info( 'Reached OOM, the number of items is {0}'.format( itemCount))


        # delete some things


        # do some more adds, verify they work up to a point

    """

    # NRU Eviction - in general fully populate memory and then add more kvs and see what keys are
    # evicted it should be the ones least recently used. So in order:
    1. Populate a bunch of kvs past memory being full and then populate some more and verify the oldest ones are deleted
    2. Populate a bunch of keys past memory being full and then access selected keys deep in the history and populate some
       more and verify that the accessed ones are not deleted
    3. Test the various ways of accessing: get, put, upsert, upsert_multi, replace, append, prepend, luck, touch
       The above is generally taken from here http://docs.couchbase.com/sdk-api/couchbase-python-client-2.2.1/api/couchbase.html


    """

    """
       test_ephemeral_bucket_NRU_eviction - this is the most basic test, populate 10% past OOM and
       see which 10% is deleted. Note that there is a concept of chunk, let's say it takes n items to
       fill up memory and we add 10% more. That makes 11 chunks and 1 first chunk should generally be deleted.
       And we can make the 10% a parameter - let's say we cycle memory completely, then all the initial kvs should
       be deleted and the new ones should reamin
    """

    KEY_ROOT = 'key-root'
    def test_ephemeral_bucket_NRU_eviction(self):

        generate_load = BlobGenerator(EvictionKV.KEY_ROOT, 'param2', self.value_size, start=0, end=self.num_items)
        self._load_all_ephemeral_buckets_until_no_more_memory(self.servers[0], generate_load, "create", 0, self.num_items)


        # figure out how many items were loaded and load 10% more
        rest = RestConnection(self.servers[0])
        itemCount = rest.get_bucket(self.buckets[0]).stats.itemCount

        self.log.info( 'Reached OOM, the number of items is {0}'.format( itemCount))



        incremental_kv_population = BlobGenerator(EvictionKV.KEY_ROOT, 'param2', self.value_size, start=itemCount, end=itemCount * 1.1)
        self._load_bucket(self.buckets[0], self.master, incremental_kv_population, "create", exp=0, kv_store=1)


        # and then probe the keys that are left. For now print out a distribution but later apply some heuristic
        client = SDKClient(hosts = [self.master.ip], bucket = self.buckets[0])


        NUMBER_OF_CHUNKS = 11
        items_in_chunk = int(1.1 * itemCount / NUMBER_OF_CHUNKS)
        for i in range(NUMBER_OF_CHUNKS):
            keys_still_present = 0
            for j in range( items_in_chunk):
                rc = client.get( EvictionKV.KEY_ROOT + str(i*items_in_chunk + j),no_format=True)

                if rc[2] is not None:
                    keys_still_present = keys_still_present + 1


            self.log.info('Chunk {0} has {1:.2f} percent items still present'.
                          format(i, 100 * keys_still_present / (itemCount*1.1/NUMBER_OF_CHUNKS) ) )

    # more tests:
    #  - recent operations exclude a key from deletion
    #  - enumerate those operations http://docs.couchbase.com/sdk-api/couchbase-python-client-2.2.1/api/couchbase.html#couchbase.bucket.Bucket.get


    """
    General idea - populate until OOM, access some kvs we think would be delete. Populate some more so that deletion
    happens around the accessed keys and verify that the accessed keys are not deleted
    """

    def test_ephemeral_bucket_NRU_eviction_access_in_the_delete_range(self):

        """
        generate_load = BlobGenerator(EvictionKV.KEY_ROOT, 'param2', self.value_size, start=0, end=self.num_items)
        self._load_all_ephemeral_buckets_until_no_more_memory(self.servers[0], generate_load, "create", 0, self.num_items)


        # figure out how many items were loaded and load 10% more
        rest = RestConnection(self.servers[0])
        itemCount = rest.get_bucket(self.buckets[0]).stats.itemCount

        self.log.info( 'Reached OOM, the number of items is {0}'.format( itemCount))


        """



        # select some keys which we expect to be adjacent to the kvs which will be deleted
        # and how many KVs should we select, maybe that is a parameter

        itemCount = 50000
        max_delete_value = itemCount / 10
        NUM_OF_ACCESSES = 50
        keys_to_access = set()
        for i in range(NUM_OF_ACCESSES):
            keys_to_access.add( random.randint(0,max_delete_value))




        # and then do accesses on the key set
        client = SDKClient(hosts = [self.master.ip], bucket = self.buckets[0])
        for i in keys_to_access:
            # and we may want to parameterize the get at some point
            rc = client.get( EvictionKV.KEY_ROOT + str(i),no_format=True)


        # and then do puts to delete out stuff
        PERCENTAGE_TO_ADD = 10
        incremental_kv_population = BlobGenerator(EvictionKV.KEY_ROOT, 'param2',
                                          self.value_size, start=itemCount, end=itemCount * PERCENTAGE_TO_ADD/100)
        self._load_bucket(self.buckets[0], self.master, incremental_kv_population, "create", exp=0, kv_store=1)


        # and verify that the touched kvs are still there
        for i in keys_to_access:
            # and we may want to parameterize the get at some point
            rc = client.get( EvictionKV.KEY_ROOT + str(i),no_format=True)
            self.assertFalse( rc is None, 'Key {0} was incorrectly deleted'.format(EvictionKV.KEY_ROOT + str(i)))




