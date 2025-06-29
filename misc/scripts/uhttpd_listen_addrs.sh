#!/bin/sh

. /lib/functions/network.sh


# Find the correct firewall zone and grab interfaces
find_fw_zone() {
  local _idx=0
  while true; do
    if zname="$(uci -q get firewall.@zone[${_idx}].name)"; then
      if [ "${zname}" == "${2}" ]; then
        eval "${1}=${_idx}"
        break;
      fi
    fi
  done
}

get_zone_ipaddrs() {
  local _addr
  local _list4=""
  local _list6=""

  for iface in ${3}; do
    if network_get_ipaddrs _addr "${iface}"; then
      _list4="${_list4:+${_list4} }${_addr}"
    fi
    _addr=
    if network_get_ipaddrs6 _addr "${iface}"; then
      _list6="${_list6:+${_list6} }${_addr}"
    fi
  done

  [ -n "${_list4}" ] && export "${1}=${_list4}"
  [ -n "${_list6}" ] && export "${2}=${_list6}"
}


# Find all addresses of all interfaces on 'lan' zone
zone_idx=
find_fw_zone zone_idx "lan"
[ -z "${zone_idx}" ] && exit 0

zones="$(uci -q get firewall.@zone[${zone_idx}].network)"
ip4addrs=
ip6addrs=

network_flush_cache
get_zone_ipaddrs ip4addrs ip6addrs "${zones}"

# Bail if nothing was found
if [ -z "${ip4addrs}" ] && [ -z "${ip6addrs}" ]; then
  exit 0
fi

# Delete previous listen addresses
uci delete uhttpd.main.listen_http
uci delete uhttpd.main.listen_https

if [ -n "${ip4addrs}" ]; then
  for ip4 in ${ip4addrs}; do
    logger -t uhttpd-addrs "Adding IPv4 listen address: \"${ip4}\""
    uci add_list uhttpd.main.listen_http="${ip4}:80"
    uci add_list uhttpd.main.listen_https="${ip4}:443"
  done
fi

if [ -n "${ip6addrs}" ]; then
  for ip6 in ${ip6addrs}; do
    # Only add the link local/ULA IPV6 addresses
    case "${ip6}" in
      f[cd]??:*)
        logger -t uhttpd-addrs "Adding IPv6 listen address: \"[${ip6}]\""
        uci add_list uhttpd.main.listen_http="[${ip6}]:80"
        uci add_list uhttpd.main.listen_https="[${ip6}]:443"
      ;;
    esac
  done
fi

# Ensure that we use/redirect to HTTPS always
uci set uhttpd.main.redirect_https='1'

uci commit uhttpd
service uhttpd restart
service uhttpd enable
