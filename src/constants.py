SNAP_COMMON_PATH = "/var/snap/juju-dns/common"
JUJU_DNS_PLUGIN_CONFIG_PATH = f"{SNAP_COMMON_PATH}/juju-dns-config.yaml"
COREFILE_PATH = f"{SNAP_COMMON_PATH}/Corefile"
JUJU_DNS_SNAP_NAME = "juju-dns"
SNAP_PACKAGES = [
    (
        JUJU_DNS_SNAP_NAME,
        {"revision": {"aarch64": "5", "x86_64": "6"}},
    )
]
