"""Common get info functions for interface"""

# Python
import os
import logging
import re
import time
from ipaddress import IPv4Network, IPv4Address

# unicon
from unicon.core.errors import SubCommandFailure

# pyATS
from ats.easypy import runtime
from ats.utils.objects import find, R
from pyats.datastructures.logic import Not

# Genie
from genie.utils.config import Config
from genie.libs.parser.utils.common import Common
from genie.libs.sdk.libs.utils.normalize import GroupKeys
from genie.metaparser.util.exceptions import SchemaEmptyParserError

# libs
from genie.libs.sdk.apis.utils import (
    int_to_mask,
    get_config_dict,
    question_mark_retrieve,
    get_delta_time_from_outputs,
)

from genie.libs.sdk.apis.iosxe.running_config.get import (
    get_running_config_section_dict,
)

log = logging.getLogger(__name__)


def get_neighbor_interface_and_device(device, interface_alias):
    """ Get neighbor interface and device from topology

        Args:
            device (`obj`): Device object
            interface_alias (`str`): interface alias

        Returns:
            Tuple: (str: neighbor interface, obj: neighbor device)

        Raises:
            None
    """
    interface = device.interfaces[interface_alias].name
    link = device.interfaces[interface_alias].link
    interface_list = link.find_interfaces(device__name=Not(device.name))

    if interface_list:
        neighbor_interface = interface_list[0]
        log.info(
            "Found interface {intf} on {device.name} has neighbor "
            "interface {neighbor_intf.name} on {neighbor_intf.device.name}".format(
                intf=interface, device=device, neighbor_intf=neighbor_interface
            )
        )
        return neighbor_interface.name, neighbor_interface.device
    else:
        return None, None


def get_interface_mtu_size(device, interface):
    """ Get interface MTU

        Args:
            device (`obj`): Device object
            interface (`str`): Interface name

        Returns:
            None
            mtu (`int`): mtu bytes

        Raises:
            None
    """
    try:
        out = device.parse(
            "show interfaces {interface}".format(interface=interface)
        )
    except SchemaEmptyParserError:
        return

    return out[interface]["mtu"]


def get_interface_mtu_config_range(device, interface):
    """ Get MTU config range

        Args:
            device (`obj`): Device object
            interface (`str`): Interface name

        Returns:
            None
            range_dict (`dict`): MTU range dict
                ex: {'min':30, 'max':360, range: '30-360'}

        Raises:
            None
    """
    range_dict = {}

    cmd = "conf t\ninterface {interface}\nmtu ".format(interface=interface)
    out = question_mark_retrieve(device, cmd, state="config")

    p = re.compile(r"<(?P<min>\d+)-(?P<max>\d+)>")
    m = p.search(out)
    if m:
        range_dict.update({"range": m.group()})
        range_dict.update({"min": int(m.groupdict()["min"])})
        range_dict.update({"max": int(m.groupdict()["max"])})
        return range_dict
    else:
        return


def get_interface_mac_address(device, interface):
    """ Get interface mac address from device

        Args:
            device (`obj`): Device object
            interface(`str`): Interface name

        Returns:
            None
            interface mac address

        Raises:
            None
    """
    log.info("Getting mac address for {} on {}".format(interface, device.name))

    try:
        out = device.parse("show interfaces {}".format(interface))
    except SchemaEmptyParserError:
        return

    return out[interface]["mac_address"]


def get_interface_without_service_policy(
    device, interface_type, virtual_interface=False
):
    """ Find a interface without service-policy

        Args:
            device (`obj`): Device object
            interface_type (`str`): Interface type
            virtual_interface ('bool'): flag for matching virtual interfaces

        Returns:
            None
            interface (`str`): Interface name

        Raises:
            None
    """
    if not virtual_interface:
        p = re.compile(r"interface +(?P<intf>(?!\S+\.\S*)\S+)")
    else:
        p = re.compile(r"interface +(?P<intf>\S+)")

    config_dict = get_running_config_section_dict(
        device, "interface"
    )
    for intf, config in config_dict.items():
        if intf.startswith("interface " + interface_type):
            cfg = "\n".join(config)
            if "service-policy" not in cfg:
                try:
                    return p.search(intf).groupdict()["intf"]
                except AttributeError:
                    continue
    else:
        return


def get_interface_qlimit_bytes(device, interface):
    """ Get interface qlimit in bytes

        Args:
            device (`obj`): Device object
            interface (`str`): Interface name

        Returns:
            None
            qlimit_bytes (`int`): Interface qlimit_bytes

        Raises:
            None
    """
    try:
        out = device.parse(
            "show platform hardware qfp active infrastructure bqs "
            "queue output default interface {interface}".format(
                interface=interface
            )
        )
    except SchemaEmptyParserError:
        return

    reqs = R(
        [
            interface,
            "index",
            "(?P<index>.*)",
            "software_control_info",
            "qlimit_bytes",
            "(?P<qlimit>.*)",
        ]
    )
    found = find([out], reqs, filter_=False, all_keys=True)
    if found:
        keys = GroupKeys.group_keys(
            reqs=reqs.args, ret_num={}, source=found, all_keys=True
        )
        return keys[0]["qlimit"]
    else:
        return


def get_interface_ip_address(device, interface):
    """ Get interface ip_address from device

        Args:
            interface('str'): Interface to get address
            device ('obj'): Device object

        Returns:
            None
            interface ip_address ('str')

        Raises:
            None
    """
    log.info(
        "Getting interface address for {interface} on {device}".format(
            interface=interface, device=device.name
        )
    )
    try:
        out = device.parse("show ip interface brief {i}".format(i=interface))
    except SchemaEmptyParserError as e:
        return

    address = out["interface"].get(interface, {}).get("ip_address", None)
    if interface not in out["interface"]:
        return
    elif (
        "ip_address" not in out["interface"][interface]
        or address == "unassigned"
    ):
        return

    return out["interface"][interface]["ip_address"]


def get_interface_loopback_ip_address(device, num=1):
    """ Gets all loopback interface ip_address' up to number specified

        Args:
            device ('obj'): device to use
            num ('int'): max number of loopback interfaces to get ip_address from

        Returns:
            list: [(interface with Loopback address, ip_address), ...]

        Raises:
            None
    """
    try:
        out = device.parse("show ip interface brief | include Loopback")
    except SchemaEmptyParserError:
        return []

    count = 0
    ip_addresses = []
    for intf in sorted(out["interface"].keys()):
        if "Loopback" in intf:
            count += 1
            ip_addresses.append((intf, out["interface"][intf]["ip_address"]))
            if count == num:
                break

    return ip_addresses


def get_unused_loopback_interface(device):
    """ Gets the first un-used loopback interface

        Args:
            device ('obj'): device to use

        returns:
            string: first unused loopback

        Raises:
            None
    """
    try:
        out = device.parse("show ip interface brief | include Loopback")
    except SchemaEmptyParserError:
        return "Loopback0"

    if out:
        # Get last used loopback address
        loopback = sorted(out["interface"].keys())[-1]

        # get loopback number and increment by 1
        return "Loopback{}".format(int(loopback[len("Loopback") :]) + 1)


def get_interface_with_mask(device, netmask="30", address_family="ipv4"):
    """ Gets interface:ip_address with specific mask

        Args:
            device('obj'): device to use
            netmask('str'): netmask the interface must have
            address_family('str'): address_family to search under

        Returns:
            (None, None)
            (interface('str'), ip_address('str'))

        Raises:
            None
    """
    try:
        out = device.parse("show interfaces")
    except SchemaEmptyParserError:
        return None, None

    for intf in out:
        if address_family in out[intf]:
            for ip in out[intf][address_family]:
                if out[intf][address_family][ip]["prefix_length"] == str(
                    netmask
                ):
                    ip_address = out[intf][address_family][ip]["ip"]
                    interface = intf
                    return interface, ip_address

    return None, None


def get_interface_with_up_state(
    device, interface_type, virtual_interface=None
):
    """ Get a interface which is up

        Args:
            device ('obj'): Device object
            interface_type ('str'): Interface type
            virtual_interface ('bool'): Flag for logical interface
                               if is None, return physical or logical
                               if is True, return only logical
                               if is False, return only physical
        Returns:
            None
            interface name ('str')

        Raises:
            None
    """
    cmd = "show ip interface | include ^{type}".format(type=interface_type)
    try:
        out = device.parse(cmd)
    except SchemaEmptyParserError:
        return

    for interface, interface_data in out.items():
        if interface_data["oper_status"] == "up":
            if virtual_interface is None:
                return interface
            elif virtual_interface == ("." in interface):
                return interface


def get_interface_carrier_delay(device, interface, delay_type):
    """ Get interface carrier delay

        Args:
            device ('obj'): Device object
            interface ('str'): Interface name
            delay_type ('str'): Carrier delay type: 'up', 'down'

        Returns:
            None
            delay in seconds ('str')

        Raises:
            None
    """
    try:
        out = device.parse("show interfaces {intf}".format(intf=interface))
    except SchemaEmptyParserError:
        return

    intf_dict = out[interface]
    key = "carrier_delay_" + delay_type
    if key in intf_dict:
        return intf_dict[key]


def get_interface_ip_and_mask(device, interface, prefix=False):
    """ Get interface ip address and mask

        Args:
            device (`obj`): Device object
            interface (`str`): Interface name
            prefix (`bool`): return ip with prefix if True
                             otherwise return ip and mask

        Returns:
            Tuple: (None, None)
            Tuple: (str: interface ip address, str: interface mask)

        Raises:
            None
    """
    ip = mask = None
    try:
        out = device.parse("show interfaces {}".format(interface))
    except SchemaEmptyParserError:
        return None, None

    for interface, interface_data in out.items():
        if "ipv4" in interface_data.keys():
            for ipv4, ip_data in interface_data["ipv4"].items():
                if prefix:
                    ip = ipv4
                else:
                    ip = ip_data["ip"]
                mask = int_to_mask(ip_data["prefix_length"])
                break

    return ip, mask


def get_interface_interfaces(device, link_name=None, opposite=False, num=0):
    """ Get interface and device

        Args:
            device ('obj'): Device object
            link_name ('str'): link name
            opposite ('bool'): find opposite device interface
            num ('int'): num of interface to return

        Returns:
            topology dictionary

        Raises:
            None
    """
    if link_name:
        link = device.interfaces[link_name].link
        intf_list = link.find_interfaces(
            device__name=Not(device.name) if opposite else device.name
        )
    else:
        intf_list = device.find_interfaces()

    if intf_list:
        intf_list.sort()

        if num > 0 and num <= len(intf_list):
            return intf_list[num - 1]

        return intf_list
    else:
        return {}


def get_interface_interfaces_under_vrf(device, vrf):
    """ Get interfaces configured under specific Vrf

        Args:
            device (`obj`): Device object
            vrf (`str`): Vrf name

        Returns:
            interfaces (`list`): List of interfaces

        Raises:
            None
    """

    try:
        out = device.parse("show vrf {}".format(vrf))
    except SchemaEmptyParserError:
        return []

    if (
        out
        and "vrf" in out
        and vrf in out["vrf"]
        and "interfaces" in out["vrf"][vrf]
    ):
        interfaces = out["vrf"][vrf]["interfaces"]
        return interfaces

    return []


def get_interface_running_config(device, interface):
    """ Get interface configuration from show running-config interface {interface}
        
        Args:
            device ('obj'): Device object
            interface ('str'): interface name

        Return:
            Dictionary with running interface configuration

        Raises:
            None
    """

    interface = Common.convert_intf_name(interface)

    try:
        output = device.execute(
            "show running-config interface {interface}".format(
                interface=interface
            )
        )
    except SubCommandFailure:
        return {}

    return get_config_dict(output)


def get_interface_packet_counter(
    device, interface, counter_field, output=None
):
    """ Returns packet counters for given interface

        Args:
            device ('obj') : Device object
            interface ('str'): Interface name
            output ('dict'): Parsed output from 'show interfaces' command

        Returns
            counter: number of output packet

        Raises:
            None
    """
    if not output:
        try:
            output = device.parse(
                "show interfaces {intf}".format(intf=interface)
            )
        except SchemaEmptyParserError:
            return

    counter = output[interface].get("counters", {}).get(counter_field, None)
    return counter


def get_neighboring_device_interface(device, testbed, interface):
    """ Get neighbor device interface

        Args:
            device ('obj'): Device object
            testbed ('obj'): Testbed object
            interface ('str'): interface name

        Returns:
            Dictionary: topology

        Raises:
            None
    """
    log.info(
        "Finding the neighbor device of the uplink interface : {interface}".format(
            interface=interface
        )
    )

    topology_devices = {}
    link = testbed.find_links().pop()
    for it in link.find_interfaces():
        if it.device == device:
            uplink_var = "uplink1"
        else:
            uplink_var = "uplink2"
        topology_devices.setdefault(uplink_var, {}).setdefault("name", it.name)
        topology_devices[uplink_var]["device"] = it.device

    if topology_devices["uplink2"]["name"]:
        log.info(
            "Successfully found neighbor device : {neighbor_device} "
            "for interface : {interface}".format(
                neighbor_device=topology_devices["uplink2"]["name"],
                interface=topology_devices["uplink2"]["device"],
            )
        )
    else:
        return {}
    return topology_devices


def get_interface_connected_adjacent_router_interfaces(
    device, link_name, num=1
):
    """ Get list of connected interfaces from adjacents routers

        Args:
            device ('obj'): Device object
            link_name ('str'): Interface alias in topology
            num ('int'): Number of interfaces to return

        Returns:
            List: EthernetInterface objects

        Raises:
            None
    """

    try:
        interface = device.interfaces[link_name]
    except KeyError:
        return

    remote_interfaces = list(interface.remote_interfaces)

    if not remote_interfaces:
        return

    return remote_interfaces[0:num]


def get_bundled_interface(device, port_channel, exclude_interface=None):
    """ Pick up Port channel bundled interface

        Args:
            device (`obj`): Device object
            port_channel (`str`): Port Channel Interface
            exclude_interface ('str'): interface to skip

        Returns:
            String: Interface

        Raises:
            None
    """
    out = device.parse("show etherchannel summary")

    if (
        out
        and "interfaces" in out
        and port_channel.capitalize() in out["interfaces"]
        and "members" in out["interfaces"][port_channel.capitalize()]
    ):
        for intf in out["interfaces"][port_channel.capitalize()]["members"]:
            if out["interfaces"][port_channel.capitalize()]["members"][intf][
                "bundled"
            ]:
                if exclude_interface and intf == exclude_interface:
                    continue
                return intf


def get_interface_address_mask_running_config(device, interface):
    """ Get interface address and mask from show running-config interface {interface}
        Args:
            device ('obj'): Device object
            interface('str'): Interface name

        Returns:
            (Interface IP address, Interface Mask)

        Raise:
            None
    """

    # ip address 192.168.10.254 255.255.255.0
    r1 = re.compile(r"ip\s+address\s+(?P<address>\S+)\s+(?P<mask>\S+)")

    interface = Common.convert_intf_name(interface)

    try:
        output = device.execute(
            "show running-config interface {interface}".format(
                interface=interface
            )
        )
    except SubCommandFailure:
        return None, None

    if not output:
        return None, None

    for line in output.splitlines():
        line = line.strip()

        result = r1.match(line)
        if result:
            group = result.groupdict()
            ip_address = group["address"]
            mask = group["mask"]
            return ip_address, mask


def get_interface_packet_output_rate(device, interface, seconds=60):
    """ Get rate of output packet in interface seconds apart

        Args:
            device ('obj'): Device object
            interface ('str'): Interface name
            seconds ('int'): Seconds to wait between show commands

        Returns:
            Traffic rate

        Raises:
            None
    """

    if seconds <= 0:
        return

    try:

        output_before = device.execute(
            "show interfaces {intf}".format(intf=interface)
        )

        log.info("Waiting {secs} seconds".format(secs=seconds))
        time.sleep(seconds)

        output_after = device.execute(
            "show interfaces {intf}".format(intf=interface)
        )

        parsed_output_before = device.parse(
            "show interfaces {intf}".format(intf=interface),
            output=output_before,
        )
        parsed_output_after = device.parse(
            "show interfaces {intf}".format(intf=interface),
            output=output_after,
        )

        delta_time = get_delta_time_from_outputs(
            output_before=output_before, output_after=output_after
        )

        counter_before = get_interface_packet_counter(
            device=device,
            interface=interface,
            counter_field="out_pkts",
            output=parsed_output_before,
        )
        if not counter_before:
            return

        counter_after = get_interface_packet_counter(
            device=device,
            interface=interface,
            counter_field="out_pkts",
            output=parsed_output_after,
        )
        if not counter_after:
            return

        output_rate = round((counter_after - counter_before) / delta_time, 2)

    except SchemaEmptyParserError as e:
        return
    except ValueError as e:
        return

    log.info(
        "Packet output rate for interface {intf} is {count}".format(
            intf=interface, count=output_rate
        )
    )

    return output_rate


def get_interface_switchport_access_vlan(device, interface):
    """ Returns access_vlan id for interface on device

        Args:
            device ('obj'): device to run on
            interface ('str'): interface to search under

        Returns:
            str access_vlan

        Raise:
            None
    """
    log.info("Getting access_vlan under {}".format(interface))

    try:
        out = device.parse("show interfaces switchport")
    except SchemaEmptyParserError:
        return None

    if out and interface in out and "access_vlan" in out[interface]:
        return out[interface]["access_vlan"]


def get_interface_netmask(ip_address):
    """ Get netmask of ip address' class

        Args:
            ip_address ('str'): ipv4 address

        Returns:
            ip address mask

        Raises:
            None
    """

    class_a = IPv4Address("127.0.0.0")
    class_b = IPv4Address("191.255.0.0")
    class_c = IPv4Address("223.255.255.0")
    ip_addr = IPv4Address(ip_address)
    ip_class = [("/8", class_a), ("/16", class_b), ("/24", class_c)]

    for e in ip_class:
        if ip_addr < e[1]:
            return e[0]


def get_interface_port_channel_members(device, interface):
    """ Get interface members

        Args:
            device ('obj'): Device object
            interface ('str'): interface to search member for

        Returns:
            interface members

        Raises:
            None
    """
    try:
        out = device.parse("show interfaces {}".format(interface))
    except SchemaEmptyParserError:
        return

    try:
        return out[interface]["port_channel"]["port_channel_member_intfs"]
    except KeyError:
        return
