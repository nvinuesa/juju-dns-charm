#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

from config import Config
import logging
from jinja2 import Template
import subprocess
from constants import CONTROLLER_RELATION, COREFILE_PATH, JUJU_DNS_SNAP_NAME, SNAP_PACKAGES,JUJU_DNS_PLUGIN_CONFIG_PATH
import os
import pwd
import ops
from ops.framework import StoredState
from ops.charm import (
    ActionEvent,
    RelationDepartedEvent,
    RelationEvent,
    RelationJoinedEvent,
)
import platform
from charms.operator_libs_linux.v2 import snap

logger = logging.getLogger(__name__)

class JujuDnsCharm(ops.CharmBase):
    _stored = StoredState()

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        framework.observe(self.on.start, self._on_start)
        framework.observe(self.on.install, self._on_install)
        framework.observe(self.on.config_changed, self._on_config_changed)
        framework.observe(self.on.set_password_action, self._on_set_password)
        framework.observe(self.on[CONTROLLER_RELATION].relation_joined, self._on_relation_joined)
        self._stored.set_default(port=1053,ttl="60",username="",password="",address="",controller="")
        port=ops.Port('udp', 1053)
        self.unit.set_ports(port)

    def _on_start(self, event: ops.StartEvent):
        """Handle start event."""
        self.unit.status = ops.ActiveStatus()

    def _on_install(self, event: ops.InstallEvent):
        """Handle install event."""
        self.unit.status = ops.MaintenanceStatus("Installing juju-dns snap")

        for snap_name, snap_version in SNAP_PACKAGES:
            try:
                snap_cache = snap.SnapCache()
                snap_package = snap_cache[snap_name]

                if not snap_package.present:
                    if revision := snap_version.get("revision"):
                        try:
                            revision = revision[platform.machine()]
                        except Exception:
                            logger.error("Unavailable snap architecture %s", platform.machine())
                            raise
                        channel = snap_version.get("channel", "")
                        snap_package.ensure(
                            snap.SnapState.Latest, revision=revision, channel=channel
                        )
                        snap_package.hold()
                    else:
                        snap_package.ensure(snap.SnapState.Latest, channel=snap_version["channel"])
            except (snap.SnapError, snap.SnapNotFoundError) as e:
                logger.error(
                    "An exception occurred when installing %s. Reason: %s", snap_name, str(e)
                )
                raise

        self.unit.status = ops.ActiveStatus("Ready")

    def _on_config_changed(self, event: ops.ConfigChangedEvent):
        """Handle config changed event."""

        # First open the port if it changed:
        if self.config["port"] != self._stored.port:
            self._stored.port = ops.Port('udp',self.config["port"])
            port=ops.Port('udp', self._stored.port)
            self.unit.set_ports(port)
            # Dump Corefile with the updated port
            self._render_corefile()

        # Update the ttl of the DNS records:
        if self.config["ttl"] != self._stored.ttl:
            logger.info("config updated with new ttl value '%s'", self.config["ttl"])
            self._stored.ttl = self.config["ttl"]
            # Dump config yaml.
            self._render_config()

    def _on_set_password(self, event: ActionEvent) -> None:
        """Set the password for the specified user."""

        username = event.params.get("username")
        password = event.params.get("password")

        if username != self._stored.username or password != self._stored.password:
            self._stored.username=username
            self._stored.password=password
            self._render_config()

    def _render_config(self) -> None:
        """Render the juju-dns config file with the stored contents."""

        # Load the config template.
        with open("templates/juju-dns-config.yaml.j2", "r") as file:
            template = Template(file.read())

        config = template.render(
            controller=self._stored.controller,
            address=self._stored.address,
            username=self._stored.username,
            password=self._stored.password,
            ttl=self._stored.ttl
        )
        logger.info("Rendered config:\n%s", config)

        with open(JUJU_DNS_PLUGIN_CONFIG_PATH, "w") as file:
            file.write(config)
        os.chmod(JUJU_DNS_PLUGIN_CONFIG_PATH, 0o640)

        self._restart_snap()

    def _render_corefile(self) -> None:
        """Render CoreDNS Corefile with the port value."""

        # Load the config template.
        with open("templates/Corefile.j2", "r") as file:
            template = Template(file.read())

        corefile = template.render(
            port=self._stored.port
        )
        logger.info("Rendered Corefile:\n%s", corefile)

        with open(COREFILE_PATH, "w") as file:
            file.write(corefile)
        os.chmod(COREFILE_PATH, 0o640)

        self._restart_snap()

    def _restart_snap(self) -> None:
        """Restart the juju-dns snap."""

        cache = snap.SnapCache()
        juju_dns_snap = cache[JUJU_DNS_SNAP_NAME]

        juju_dns_snap.restart()

    def _on_relation_joined(self, event: RelationJoinedEvent) -> None:
        """Add peer to replica set.

        Args:
            event: The triggering relation joined event.
        """

        self._on_relation_handler(event)

        # self._update_related_hosts(event)

    def _on_relation_handler(self, event: RelationEvent) -> None:
        """Update the controller address when joining the controller relation"""

        for unit in event.relation.units:
            if unit.app == "juju-dns":
                # This is a peer unit
                continue
            if "port" in event.relation.data[unit]:
                # We have found the leader unit (only leader unit should have
                # the port in the relation data), so use this address and break.
                self._stored.address = event.relation.data[unit]["private-address"]+":"+event.relation.data[unit]["port"]
                break
            # If no port is specified, use the default port.
            self._stored.address = event.relation.data[unit]["private-address"]+":17070"

        # Now that we have the address, also add the controller (model, because
        # this charm is supposed to be deployed on the controller model) name
        # to the config and render the file.
        self._stored.controller = os.getenv["JUJU_CONTROLLER"]
        self._render_config()


    def _update_related_hosts(self, event) -> None:
        # app relations should be made aware of the new set of hosts
        return

if __name__ == "__main__":  # pragma: nocover
    ops.main(JujuDnsCharm)  # type: ignore
