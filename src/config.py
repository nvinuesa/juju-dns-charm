# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

class Config:
    """Configuration for Juju internal DNS Charm."""

    port: int
    ttl: int
    controller: str
    address: str
    username: str
    password: str
