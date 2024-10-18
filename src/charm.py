#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from jinja2 import Template
import yaml
import subprocess
from constants import COREFILE_PATH, JUJU_DNS_SNAP_NAME, SNAP_PACKAGES,JUJU_DNS_PLUGIN_CONFIG_PATH
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
    controllers = {}

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        framework.observe(self.on.start, self._on_start)
        framework.observe(self.on.install, self._on_install)
        framework.observe(self.on.config_changed, self._on_config_changed)
        self._stored.set_default(port=1053, ttl="60")
        port=ops.Port('udp', 1053)
        self.unit.set_ports(port)


    def _on_start(self, event: ops.StartEvent):
        """Handle start event."""
        self.unit.status = ops.ActiveStatus()

    def _on_install(self, event: ops.InstallEvent):
        """Handle install event."""
        self.unit.status = ops.MaintenanceStatus("Installing juju-dns snap")

        # Load controllers and accounts resources.
        try:
            accounts_path = self.model.resources.fetch("accounts")
        except Exception as e:
            logger.error("retrieving accounts.yaml file path from resources, reason: %s", str(e))
            raise
        try:
            controllers_path = self.model.resources.fetch("controllers")
        except Exception as e:
            logger.error("retrieving controllers.yaml file path from resources, reason: %s", str(e))
            raise

        with open(accounts_path, "r") as file:
            accounts_contents = yaml.safe_load(file)
        with open(controllers_path, "r") as file:
            controllers_contents = yaml.safe_load(file)

        for controller_name in controllers_contents["controllers"]:
            self.controllers[controller_name]={}
            self.controllers[controller_name]["address"] = controllers_contents["controllers"][controller_name]["api-endpoints"][0]
            self.controllers[controller_name]["username"] = accounts_contents["controllers"][controller_name]["user"]
            self.controllers[controller_name]["password"] = accounts_contents["controllers"][controller_name]["password"]

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

        logger.info("controllers %r", self.controllers)
        self._render_config()

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

    def _render_config(self) -> None:
        """Render the juju-dns config file with the stored contents."""

        # Load the config template.
        with open("templates/juju-dns-config.yaml.j2", "r") as file:
            template = Template(file.read())

        config = template.render(
            controllers=self.controllers,
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

if __name__ == "__main__":  # pragma: nocover
    ops.main(JujuDnsCharm)  # type: ignore
