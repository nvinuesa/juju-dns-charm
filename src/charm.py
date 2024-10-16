#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

from config import Config
import logging
from jinja2 import Template
import subprocess
from constants import COREFILE_PATH, JUJU_DNS_SNAP_NAME, SNAP_PACKAGES,JUJU_DNS_PLUGIN_CONFIG_PATH
import os
import pwd
import ops
from ops.framework import StoredState
from ops.charm import (
    ActionEvent,
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
        self._stored.set_default(port=ops.Port('udp', 1053),ttl="60",username="",password="")
        self.unit.set_ports(self._stored.port)

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
        if self.config["port"] != self._stored.port.port:
            self._stored.port = ops.Port('udp',self.config["port"])
            self.unit.set_ports(self._stored.port)
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
            controller="c",
            address="10.165.241.216:17070",
            username=self._stored.username, password=self._stored.password,
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
