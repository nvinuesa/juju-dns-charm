# Copyright 2024 nicolas
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import unittest

import ops
import ops.testing
from charm import JujuDnsCharm


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = ops.testing.Harness(JujuDnsCharm)
        self.addCleanup(self.harness.cleanup)

    def test_start(self):
        # Simulate the charm starting
        self.harness.begin_with_initial_hooks()

        # Ensure we set an ActiveStatus with no message
        self.assertEqual(self.harness.model.unit.status, ops.ActiveStatus())

    def test_new_http_relation(self):
        # Before the test begins, we have integrated a remote app
        # with this charm, so we call add_relation() before begin().
        relation_id = self.harness.add_relation('smtp', 'consumer_app')
        self.harness.begin()
        # For the test, we simulate a unit joining the relation.
        self.harness.add_relation_unit()
        assert 'smtp_credentials’ in harness.get_relation_data(relation_id, 'consumer_app/0' )

    def test_db_relation_broken(self):
        relation_id = self.harness.add_relation('website', 'http')
        self.harness.begin()
        self.harness.remove_relation(relation_id)
        assert self.harness.charm.get_http() is None

    def test_receive_db_credentials(self):
        relation_id = self.harness.add_relation('website', 'http')
        self.harness.begin()
        self.harness.update_relation_data(relation_id, self.harness.charm.app, {'credentials-id': 'secret:xxx'})
        assert self.harness.charm.db_tables_created()
