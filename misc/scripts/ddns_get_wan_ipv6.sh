#!/bin/sh
. /lib/functions/network.sh
network_flush_cache
network_find_wan6 NET_IF6
network_get_ipaddr6 NET_ADDR6 "${NET_IF6}"
echo "${NET_ADDR6}"

