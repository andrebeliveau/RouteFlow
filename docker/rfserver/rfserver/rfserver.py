#!/usr/bin/env python
#-*- coding:utf-8 -*-

import os
import sys
import logging
import binascii
import argparse
import time
import copy
import Queue
import threading
import sys
sys.path.append("../")

from bson.binary import Binary

import rflib.ipc.IPC as IPC
import rflib.ipc.IPCService as IPCService
from rflib.ipc.RFProtocol import *
from rflib.ipc.RFProtocolFactory import RFProtocolFactory
from rflib.defs import *
from rflib.types.Match import *
from rflib.types.Action import *
from rflib.types.Option import *
from rflib.types.Band import *

from rftable import *
from rffastpath import *

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(name)-15s %(levelname)-8s %(message)s',
    datefmt='%b %d %H:%M:%S'
    )

# Register actions
REGISTER_IDLE = 0
REGISTER_ASSOCIATED = 1
REGISTER_ISL = 2

class RouteModTranslator(object):

    DROP_PRIORITY = Option.PRIORITY(PRIORITY_LOWEST + PRIORITY_BAND)
    ESTABLISH_PRIORITY = Option.PRIORITY(PRIORITY_LOWEST + PRIORITY_BAND + 1)
    CONTROLLER_PRIORITY = Option.PRIORITY(PRIORITY_HIGH)
    FASTPATH_PRIORITY = Option.PRIORITY(PRIORITY_HIGH + 1)
    DEFAULT_PRIORITY = Option.PRIORITY(PRIORITY_LOWEST + PRIORITY_BAND + 1000)

    #The table used to tag fastpath packets
    FP_TABLE = 1

    def __init__(self, dp_id, ct_id, rftable, isltable, conf, islconf, fpconf, log, labeller):
        self.dp_id = dp_id
        self.ct_id = ct_id
        self.rftable = rftable
        self.isltable = isltable
        self.fpconf = fpconf
        self.islconf = islconf
        self.conf = conf
        self.labeller = labeller
        self.log = log

    def configure_datapath(self):
        raise Exception

    def handle_controller_route_mod(self, entry, rm):
        raise Exception

    def handle_route_mod(self, entry, rm):
        raise Exception

    def handle_isl_route_mod(self, entry, rm):
        raise Exception

    def _get_fastpath_port(self):
        """Returns the fastpath port towards the controller"""
        master = []
        fpentries = self.fpconf.get_entries_for_dpid(self.ct_id, self.dp_id)
        fpentries += self.islconf.get_entries_by_dpid(self.ct_id, self.dp_id)
        for fp in fpentries:
            if hasattr(fp, "fp_master") and fp.fp_master:
                if fp.fp_master != self.dp_id:
                    master.append(fp)

        if len(master) != 1:
            self.log.error("We expect a single master fastpath link not %d" % len(master))
            if len(master) == 0:
                return None
        master = master[0]

        if master.dp_id == self.dp_id and master.ct_id == self.ct_id:
            master_port = master.dp_port
        else:
            master_port = master.rem_port
        return master_port

    def _register_fastpaths(self, usetables):
        """Adds rules for all fastpaths that traverse or are created by this forwarding element"""
        rms = []
        # Treat fastpaths and isls the same
        fpentries = self.fpconf.get_entries_for_dpid(self.ct_id, self.dp_id)
        fpentries += self.islconf.get_entries_by_dpid(self.ct_id, self.dp_id)

        master_port = self._get_fastpath_port()

        # Add entries for all directly attached ports
        ports = self.conf.get_config_for_dp(self.ct_id, self.dp_id)
        rms += self._register_fpports(master_port, ports, usetables)

        # Add entries for all fastpaths that we carry
        for fp in fpentries:
            if hasattr(fp, "fp_master") and fp.fp_master == self.dp_id:
                if fp.dp_id == self.dp_id and fp.ct_id == self.ct_id:
                    dp_port = fp.dp_port
                else:
                    dp_port = fp.rem_port
                rms += self._register_fpisl(master_port, fp, dp_port)

        return rms

    def _register_fpports(self, fp_port, ports, usetables):
        """Adds a rule for each local port to send controller traffic to the next fastpath
        or isl link"""
        rms = []
        if ports == None:
            ports = []
        for port in ports:

            if not hasattr(port, 'fp_label'):
                self.log.error("dp %d port %d has no fastpath label" %
                               (self.dp_id, port.dp_port))
                continue

            self.log.info("dp %d port %d registering fastpath %s" %
                          (self.dp_id, port.dp_port, port.fp_label))

            # Add rule to tag for every incoming packet based on inport
            # in our tagging table
            if usetables:
                rm = RouteMod(RMT_ADD, self.dp_id)
                rm.add_match(Match.IN_PORT(port.dp_port))
                self.labeller.rfaction_push_meta(port.fp_label, rm)
                rm.add_action(Action.OUTPUT(fp_port))
                rm.add_option(self.CONTROLLER_PRIORITY)
                rm.set_table(self.FP_TABLE)
                rms.append(rm)

            # For each incomming fp packet set the correct output port
            rm = RouteMod(RMT_ADD, self.dp_id)
            rm.add_match(Match.IN_PORT(fp_port))
            self.labeller.rfmatch_meta(port.fp_label, rm)
            self.labeller.rfaction_pop_meta(rm)
            rm.add_action(Action.OUTPUT(port.dp_port))
            rm.add_option(self.FASTPATH_PRIORITY)
            rms.append(rm)

        return rms

    def _register_fpisl(self, out_port, isl, dp_port):
        """Adds entries for all fastpaths carried over an isl by putting rules
        into this switch"""
        rms = []

        for label, _ in isl.fast_paths:
            # Add rule to forward match packets towards the controller
            rm = RouteMod(RMT_ADD, self.dp_id)
            rm.add_match(Match.IN_PORT(dp_port))
            self.labeller.rfmatch_meta(label, rm)
            rm.add_action(Action.OUTPUT(out_port))
            rm.add_option(self.FASTPATH_PRIORITY)
            rms.append(rm)

            # Add rule to forward towards ports
            rm = RouteMod(RMT_ADD, self.dp_id)
            rm.add_match(Match.IN_PORT(out_port))
            self.labeller.rfmatch_meta(label, rm)
            rm.add_action(Action.OUTPUT(dp_port))
            rm.add_option(self.FASTPATH_PRIORITY)
            rms.append(rm)

        return rms


class DefaultRouteModTranslator(RouteModTranslator):

    def _send_rm_with_matches(self, rm, out_port, entries):
        rms = []
        for entry in entries:
            if out_port != entry.dp_port:
                if (entry.get_status() == RFENTRY_ACTIVE or
                    entry.get_status() == RFISL_ACTIVE):
                    local_rm = copy.deepcopy(rm)
                    local_rm.add_match(Match.ETHERNET(entry.eth_addr))
                    local_rm.add_match(Match.IN_PORT(entry.dp_port))
                    rms.append(local_rm)
        return rms

    def configure_datapath(self):
        rms = []

        # delete all groups
        rm = RouteMod(RMT_DELETE_GROUP, self.dp_id)
        rms.append(rm)

        # delete all flows
        rm = RouteMod(RMT_DELETE, self.dp_id)
        rms.append(rm)

        # catch ipv4 and ipv6 and send to the controller so we can
        # do arp and install a rule for the flow
        rm = RouteMod(RMT_ADD, self.dp_id)
        rm.add_option(self.ESTABLISH_PRIORITY)
        rm.add_match(Match.ETHERTYPE(ETHERTYPE_IP))
        rms.extend(self.handle_controller_route_mod(self,rm))

        rm = RouteMod(RMT_ADD, self.dp_id)
        rm.add_option(self.ESTABLISH_PRIORITY)
        rm.add_match(Match.ETHERTYPE(ETHERTYPE_IPV6))
        rms.extend(self.handle_controller_route_mod(self,rm))

        # default drop
        rm = RouteMod(RMT_ADD, self.dp_id)
        #rm.add_match(Match.ETHERTYPE(ETHERTYPE_IP))
        rm.add_option(self.DROP_PRIORITY)
        rms.append(rm)

        # ARP
        rm = RouteMod(RMT_ADD, self.dp_id)
        rm.add_match(Match.ETHERTYPE(ETHERTYPE_ARP))
        rm.add_option(self.CONTROLLER_PRIORITY)
        rms.extend(self.handle_controller_route_mod(self, rm))

        # Register fastpath rules
        if self.fpconf.enabled:
            rms += self._register_fastpaths(False)

        return rms

    def handle_controller_route_mod(self, entry, rm):
        if self.fpconf.enabled:
            rms = []
            master_port = self._get_fastpath_port()

            # If this only applies to a single port we only install for that
            for match in rm.get_matches():
                if Match.from_dict(match)._type == RFMT_IN_PORT:
                    port = self.conf.get_config_for_dp_port(self.ct_id, self.dp_id, match.value)
                    self.labeller.rfaction_push_meta(port.fp_label, rm)
                    rm.add_action(Action.OUTPUT(master_port))
                    return [rm]

            # Install for all ports
            ports = self.conf.get_config_for_dp(self.ct_id, self.dp_id)
            if ports == None:
                ports = []
            for port in ports:
                new_rm = copy.deepcopy(rm)
                new_rm.add_match(Match.IN_PORT(port.dp_port))
                self.labeller.rfaction_push_meta(port.fp_label, new_rm)
                new_rm.add_action(Action.OUTPUT(master_port))
                rms.append(new_rm)
            return rms
        else:
            rm.add_action(Action.CONTROLLER())
        return [rm]

    def handle_route_mod(self, entry, rm):
        rms = []
        entries = self.rftable.get_entries(dp_id=entry.dp_id,
                                           ct_id=entry.ct_id)
        entries.extend(self.isltable.get_entries(dp_id=entry.dp_id,
                                                 ct_id=entry.ct_id))

        # Replace the VM port with the datapath port
        rm.add_action(Action.OUTPUT(entry.dp_port))

        rms.extend(self._send_rm_with_matches(rm, entry.dp_port, entries))
        return rms

    def handle_isl_route_mod(self, r, rm):
        rms = []
        rm.set_id(self.dp_id)
        rm.set_table(0)
        rm.set_actions(None)
        rm.add_action(Action.SET_ETH_SRC(r.eth_addr))
        rm.add_action(Action.SET_ETH_DST(r.rem_eth_addr))
        rm.add_action(Action.OUTPUT(r.dp_port))
        entries = self.rftable.get_entries(dp_id=r.dp_id, ct_id=r.ct_id)
        rms.extend(self._send_rm_with_matches(rm, r.dp_port, entries))
        return rms


class SatelliteRouteModTranslator(DefaultRouteModTranslator):

    def __init__(self, dp_id, ct_id, rftable, isltable, conf, islconf, fpconf, log, labeller):
        super(SatelliteRouteModTranslator, self).__init__(
            dp_id, ct_id, rftable, isltable, conf, islconf, fpconf, log, labeller)
        self.sent_isl_dl = set()

    def handle_isl_route_mod(self, r, rm):
        rms = []
        for ethertype in (ETHERTYPE_IP, ETHERTYPE_IPV6):
            rm.set_matches(None)
            rm.add_match(Match.ETHERTYPE(ethertype))
            rm.set_options(None)
            rm.add_option(self.DEFAULT_PRIORITY)
            if r.rem_eth_addr not in self.sent_isl_dl:
                self.sent_isl_dl.add(r.rem_eth_addr)
                rm.set_id(self.dp_id)
                rm.set_table(0)
                rm.set_actions(None)
                rm.add_action(Action.SET_ETH_SRC(r.eth_addr))
                rm.add_action(Action.SET_ETH_DST(r.rem_eth_addr))
                rm.add_action(Action.OUTPUT(r.dp_port))
                entries = self.rftable.get_entries(dp_id=r.dp_id, ct_id=r.ct_id)
                rms.extend(self._send_rm_with_matches(rm, r.dp_port, entries))
        return rms


class NoviFlowMultitableRouteModTranslator(RouteModTranslator):

    FP_TABLE = 3
    FIB_TABLE = 2
    ETHER_TABLE = 1

    def __init__(self, dp_id, ct_id, rftable, isltable, conf, islconf, fpconf, log, labeller):
        super(NoviFlowMultitableRouteModTranslator, self).__init__(
            dp_id, ct_id, rftable, isltable, conf, islconf, fpconf, log, labeller)

    def _send_rm_with_matches(self, rm, out_port, entries):
        rms = []
        for entry in entries:
            if out_port != entry.dp_port:
                if (entry.get_status() == RFENTRY_ACTIVE or
                    entry.get_status() == RFISL_ACTIVE):
                    rms.append(rm)
                    break
        return rms

    def configure_datapath(self):
        rms = []

        # delete all groups
        rm = RouteMod(RMT_DELETE_GROUP, self.dp_id)
        rms.append(rm)
        # default group - send to controller
        rm = RouteMod(RMT_ADD_GROUP, self.dp_id)
        rm.set_group(CONTROLLER_GROUP);
        rm.add_action(Action.CONTROLLER())
        rms.append(rm)

        # delete all flows
        rm = RouteMod(RMT_DELETE, self.dp_id)
        rms.append(rm)

        # catch ipv4 and ipv6 and send to the controller so we can
        # do arp and install a rule for the flow
        rm = RouteMod(RMT_ADD, self.dp_id)
        rm.add_option(self.ESTABLISH_PRIORITY)
        rm.add_match(Match.ETHERTYPE(ETHERTYPE_IP))
        # Noviflow sets all controller actions on the ether table for performance reasons but this
        # will not work there. TODO test this on hardware and see if its a problem.
        rms.extend([(x.set_table(self.FIB_TABLE), x)[1] for x in self.handle_controller_route_mod(self,rm)])

        rm = RouteMod(RMT_ADD, self.dp_id)
        rm.add_option(self.ESTABLISH_PRIORITY)
        rm.add_match(Match.ETHERTYPE(ETHERTYPE_IPV6))
        rms.extend([(x.set_table(self.FIB_TABLE), x)[1] for x in self.handle_controller_route_mod(self,rm)])

        # default drop
        for table_id in (0, self.ETHER_TABLE, self.FIB_TABLE):
            rm = RouteMod(RMT_ADD, self.dp_id)
            rm.set_table(table_id)
            rm.add_option(self.DROP_PRIORITY)
            rms.append(rm)
        rm = RouteMod(RMT_ADD, self.dp_id)
        rm.add_match(Match.ETHERNET("ff:ff:ff:ff:ff:ff"))
        rm.add_action(Action.GOTO(self.ETHER_TABLE))
        rm.add_option(self.CONTROLLER_PRIORITY)
        rms.append(rm)
        # IPv6 neighbor discovery
        rm = RouteMod(RMT_ADD, self.dp_id)
        rm.add_match(Match.ETHERTYPE(ETHERTYPE_IPV6))
        rm.add_match(Match.NW_PROTO(IPPROTO_ICMPV6))
        rm.add_option(self.CONTROLLER_PRIORITY)
        rm.add_action(Action.GOTO(self.FIB_TABLE))
        rms.append(rm)
        # ARP
        rm = RouteMod(RMT_ADD, self.dp_id)
        rm.set_table(self.ETHER_TABLE)
        rm.add_match(Match.ETHERTYPE(ETHERTYPE_ARP))
        rm.add_option(self.CONTROLLER_PRIORITY)
        rms.extend(self.handle_controller_route_mod(self, rm))
        # IPv4
        rm = RouteMod(RMT_ADD, self.dp_id)
        rm.set_table(self.ETHER_TABLE)
        rm.add_match(Match.ETHERTYPE(ETHERTYPE_IP))
        rm.add_option(self.DEFAULT_PRIORITY)
        rm.add_action(Action.GOTO(self.FIB_TABLE))
        rms.append(rm)


        # Register fastpath rules
        if self.fpconf.enabled:
            rms += self._register_fastpaths(True)

        return rms

    def handle_controller_route_mod(self, entry, rm):
        rms = []
        if not self.fpconf.enabled:
            rm.add_action(Action.GROUP(CONTROLLER_GROUP))
        else:
            rm.add_action(Action.GOTO(self.FP_TABLE))
        # should be FIB_TABLE, but see NoviFlow note.
        rm.set_table(self.ETHER_TABLE)
        dl_dst = None
        orig_matches = rm.get_matches()
        rm.set_matches(None)
        for match_dict in orig_matches:
            match = Match.from_dict(match_dict)
            match_type = match.type_to_str(match._type)
            if match_type == "RFMT_ETHERNET":
                dl_dst = match
            else:
                rm.add_match(match)
        rms.append(rm)

        if dl_dst is not None:
            hw_rm = RouteMod(RMT_CONTROLLER, entry.dp_id)
            hw_rm.set_id(rm.get_id())
            hw_rm.set_vm_port(rm.get_vm_port())
            hw_rm.add_match(dl_dst)
            hw_rm.add_action(Action.GOTO(self.ETHER_TABLE))
            hw_rm.add_option(self.DEFAULT_PRIORITY)
            rms.append(hw_rm)

        return rms

    def handle_route_mod(self, entry, rm):
        rms = []
        entries = self.rftable.get_entries(dp_id=entry.dp_id,
                                           ct_id=entry.ct_id)
        entries.extend(self.isltable.get_entries(dp_id=entry.dp_id,
                                                 ct_id=entry.ct_id))

        # Replace the VM port with the datapath port
        rm.add_action(Action.OUTPUT(entry.dp_port))

        rm.set_table(self.FIB_TABLE)

        rm.set_options(None)
        rm.add_option(self.CONTROLLER_PRIORITY)

        rms.extend(self._send_rm_with_matches(rm, entry.dp_port, entries))
        return rms

    def handle_isl_route_mod(self, r, rm):
        rms = []
        rm.set_id(self.dp_id)
        rm.set_table(self.FIB_TABLE)
        rm.set_options(None)
        rm.add_option(self.CONTROLLER_PRIORITY)
        rm.set_actions(None)
        rm.add_action(Action.SET_ETH_SRC(r.eth_addr))
        rm.add_action(Action.SET_ETH_DST(r.rem_eth_addr))
        rm.add_action(Action.OUTPUT(r.dp_port))
        entries = self.rftable.get_entries(dp_id=r.dp_id, ct_id=r.ct_id)
        rms.extend(self._send_rm_with_matches(rm, r.dp_port, entries))

        # Add entry to table 0 to match the ISL MAC and passes the packet to FIB table
        rm = copy.deepcopy(rm)
        rm.set_table(0)
        rm.set_actions(None)
        rm.add_action(Action.GOTO(self.FIB_TABLE))
        rm.set_matches(None)
        if self.dp_id == r.dp_id:
            rm.add_match(Match.ETHERNET(r.eth_addr))
        else:
            rm.add_match(Match.ETHERNET(r.rem_eth_addr))
        rms.append(rm)

        return rms


class CorsaMultitableRouteModTranslator_v1(RouteModTranslator):

    DROP_PRIORITY = Option.PRIORITY(0)
    CONTROLLER_PRIORITY = Option.PRIORITY(255)
    DEFAULT_PRIORITY = Option.PRIORITY(PRIORITY_LOWEST + PRIORITY_BAND + 1)

    VLAN_MPLS_TABLE = 1
    VLAN_TABLE = 2
    MPLS_TABLE = 3 # not currently implemented
    ETHER_TABLE = 4
    COS_MAP_TABLE = 5
    FIB_TABLE = 6
    LOCAL_TABLE = 9

    def __init__(self, dp_id, ct_id, rftable, isltable, conf, islconf, fpconf, log, labeller):
        super(CorsaMultitableRouteModTranslator_v1, self).__init__(
            dp_id, ct_id, rftable, isltable, conf, islconf, fpconf, log, labeller)
        self.last_groupid = CONTROLLER_GROUP
        self.actions_to_groupid = {}

    def configure_datapath(self):
        rms = []

        # delete all groups
        rm = RouteMod(RMT_DELETE_GROUP, self.dp_id)
        rms.append(rm)

        # delete all flows
        rm = RouteMod(RMT_DELETE, self.dp_id)
        rms.append(rm)

        # default drop
        for table_id in (0, self.VLAN_TABLE,
                         self.ETHER_TABLE, self.FIB_TABLE):
            rm = RouteMod(RMT_ADD, self.dp_id)
            rm.set_table(table_id)
            rm.add_option(self.DROP_PRIORITY)
            rms.append(rm)

        ## Table 0
        rm = RouteMod(RMT_ADD, self.dp_id)
        rm.add_match(Match.ETHERNET("ff:ff:ff:ff:ff:ff"))
        rm.add_action(Action.GOTO(self.VLAN_MPLS_TABLE))
        rm.add_option(self.CONTROLLER_PRIORITY)
        rms.append(rm)

        ## VLAN/MPLS table 1
        rm = RouteMod(RMT_ADD, self.dp_id)
        rm.set_table(self.VLAN_MPLS_TABLE)
        rm.add_match(Match.ETHERTYPE(0x8100))
        rm.add_action(Action.GOTO(self.VLAN_TABLE))
        rm.add_option(self.CONTROLLER_PRIORITY)
        rms.append(rm)

        ## VLAN table 2
        # no default flows other than drop.

        ## Ether type table 3
        # ARP
        rm = RouteMod(RMT_ADD, self.dp_id)
        rm.set_table(self.ETHER_TABLE)
        rm.add_match(Match.ETHERTYPE(ETHERTYPE_ARP))
        rm.add_action(Action.CONTROLLER())
        rm.add_option(self.CONTROLLER_PRIORITY)
        rms.append(rm)
        # IPv4
        rm = RouteMod(RMT_ADD, self.dp_id)
        rm.set_table(self.ETHER_TABLE)
        rm.add_match(Match.ETHERTYPE(ETHERTYPE_IP))
        rm.add_option(self.CONTROLLER_PRIORITY)
        rm.add_action(Action.GOTO(self.COS_MAP_TABLE))
        rms.append(rm)

        # COS table 5 (just map to FIB table)
        rm = RouteMod(RMT_ADD, self.dp_id)
        rm.set_table(self.COS_MAP_TABLE)
        rm.add_action(Action.GOTO(self.FIB_TABLE))
        rm.add_option(self.DROP_PRIORITY)
        rms.append(rm)

        ## Local table temporary catch-all entry (table 9)
        rm = RouteMod(RMT_ADD, self.dp_id)
        rm.set_table(self.LOCAL_TABLE)
        rm.add_action(Action.CONTROLLER())
        rm.add_option(self.CONTROLLER_PRIORITY)
        rms.append(rm)

        return rms

    def _send_rm_with_matches(self, rm, out_port, entries):
        rms = []
        for entry in entries:
            if out_port != entry.dp_port:
                if (entry.get_status() == RFENTRY_ACTIVE or
                    entry.get_status() == RFISL_ACTIVE):
                    dst_eth = None
                    actions = rm.actions
                    rm.set_actions(None)
                    for action_dict in actions:
                        action = Action.from_dict(action_dict)
                        action_type = action.type_to_str(action._type)
                        if action_type == 'RFAT_SET_ETH_DST':
                            dst_eth = action.get_value()
                        elif action_type == 'RFAT_SWAP_VLAN_ID':
                            vlan_id = action.get_value()
                            action = Action.PUSH_VLAN_ID(vlan_id | OFPVID_PRESENT)
                        rm.add_action(action)
                    if dst_eth not in self.actions_to_groupid:
                        self.last_groupid += 1
                        new_groupid = self.last_groupid
                        self.actions_to_groupid[dst_eth] = new_groupid
                        group_rm = RouteMod(RMT_ADD_GROUP, self.dp_id)
                        group_rm.set_group(new_groupid)
                        group_rm.set_actions(rm.actions)
                        rms.append(group_rm)
                        self.log.info("adding new group %u for Ethernet destination %s" % (
                            new_groupid, dst_eth))
                    rm.set_actions(None)
                    rm.add_action(Action.GROUP(self.actions_to_groupid[dst_eth]))
                    rms.append(rm)
                    break
        return rms

    def handle_controller_route_mod(self, entry, rm):
        rms = []
        rm.add_action(Action.GOTO(self.LOCAL_TABLE))
        rm.set_table(self.FIB_TABLE)
        dl_dst = None
        dst_vlan = None
        orig_matches = rm.get_matches()
        rm.set_matches(None)
        for match_dict in orig_matches:
            match = Match.from_dict(match_dict)
            match_type = match.type_to_str(match._type)
            if match_type == "RFMT_ETHERNET":
                dl_dst = match
            # TODO: support more than IP address matches
            # TODO: support more than IPv4
            elif match_type == "RFMT_IPV4":
                rm.add_match(Match.ETHERTYPE(ETHERTYPE_IP))
                rm.add_match(match)
            elif match_type == "RFMT_VLAN_ID":
                dst_vlan = match.get_value()

        if rm.matches:
            rms.append(rm)

        if dst_vlan is not None:
            vlan_rm = RouteMod(RMT_ADD, self.dp_id)
            vlan_rm.set_table(self.VLAN_TABLE)
            vlan_rm.add_match(Match.IN_PORT(entry.dp_port))
            vlan_rm.add_match(Match.VLAN_ID(dst_vlan))
            vlan_rm.add_action(Action.STRIP_VLAN_DEFERRED())
            vlan_rm.add_action(Action.GOTO(self.ETHER_TABLE))
            vlan_rm.add_option(self.CONTROLLER_PRIORITY)
            self.log.info("adding new VLAN strip rule for VLAN %s" % (dst_vlan))
            rms.append(vlan_rm)

        if dl_dst is not None:
            hw_rm = RouteMod(RMT_CONTROLLER, entry.dp_id)
            hw_rm.set_id(rm.get_id())
            hw_rm.set_vm_port(rm.get_vm_port())
            hw_rm.add_match(dl_dst)
            hw_rm.add_action(Action.GOTO(self.VLAN_MPLS_TABLE))
            hw_rm.add_option(self.DEFAULT_PRIORITY)
            rms.append(hw_rm)

        return rms

    def handle_route_mod(self, entry, rm):
        rms = []
        entries = self.rftable.get_entries(dp_id=entry.dp_id,
                                           ct_id=entry.ct_id)
        entries.extend(self.isltable.get_entries(dp_id=entry.dp_id,
                                                 ct_id=entry.ct_id))

        # Replace the VM port with the datapath port
        rm.add_action(Action.OUTPUT(entry.dp_port))

        rm.set_table(self.FIB_TABLE)

        rms.extend(self._send_rm_with_matches(rm, entry.dp_port, entries))
        return rms

class CorsaMultitableRouteModTranslator_v3(RouteModTranslator):

    DROP_PRIORITY = Option.PRIORITY(0)
    CONTROLLER_PRIORITY = Option.PRIORITY(255)
    DEFAULT_PRIORITY = Option.PRIORITY(PRIORITY_LOWEST + PRIORITY_BAND + 1)

    PORT_BASED_PROTO_TABLE = 0
    VLAN_CHECK_TABLE = 1
    VLAN_MAC_XLATE_TABLE = 2
    VLAN_CIRCUIT_TABLE = 3
    PRIORITY_MAP_TABLE = 4
    L3_IF_MAC_DA_TABLE = 5
    ETHER_TABLE = 6
    FIB_TABLE = 7
    LOCAL_TABLE = 9

    def __init__(self, dp_id, ct_id, rftable, isltable, conf, islconf, fpconf, log, labeller): 
        super(CorsaMultitableRouteModTranslator_v3, self).__init__(
            dp_id, ct_id, rftable, isltable, conf, islconf, fpconf, log, labeller)
        self.last_groupid = CONTROLLER_GROUP
        self.actions_to_groupid = {}

    def configure_datapath(self):
        rms = []

        # delete all meters
        rm = RouteMod(RMT_DELETE_METER, self.dp_id)
        rms.append(rm)

        # delete all groups
        rm = RouteMod(RMT_DELETE_GROUP, self.dp_id)
        rms.append(rm)

        # delete all flows
        rm = RouteMod(RMT_DELETE, self.dp_id)
        rms.append(rm)

        # default meter
        rm = RouteMod(RMT_ADD_METER, self.dp_id)
        rm.set_meter(1)
        rm.set_flags(METER_FLAG_KBPS|METER_FLAG_STATS)
        MAX_RATE = 0xFFFFFFFF
        rm.add_band(Band.DROP(MAX_RATE))
        rms.append(rm)

        # default drop
        for table_id in (self.VLAN_CHECK_TABLE,
                         self.VLAN_CIRCUIT_TABLE,
                         self.L3_IF_MAC_DA_TABLE,
                         self.ETHER_TABLE,
                         self.FIB_TABLE,
                         self.LOCAL_TABLE):
            rm = RouteMod(RMT_ADD, self.dp_id)
            rm.set_table(table_id)
            rm.add_option(self.DROP_PRIORITY)
            rms.append(rm)

        ## Port Based Protocol Table 0
        rm = RouteMod(RMT_ADD, self.dp_id)
        rm.set_table(self.PORT_BASED_PROTO_TABLE)
        rm.add_action(Action.GOTO(self.VLAN_CHECK_TABLE))
        rm.add_option(self.DROP_PRIORITY)
        rms.append(rm)

        ## VLAN Check Table 1 (immutable)
        # Tagged packets to VLAN_MAC_XLATE
        rm = RouteMod(RMT_ADD, self.dp_id)
        rm.set_table(self.VLAN_CHECK_TABLE)
        rm.add_match(Match.VLAN_TAGGED(True))
        rm.add_action(Action.GOTO(self.VLAN_MAC_XLATE_TABLE))
        rm.add_option(self.CONTROLLER_PRIORITY)
        rms.append(rm)

        ## VLAN MAC XLATE Table 2
        rm = RouteMod(RMT_ADD, self.dp_id)
        rm.set_table(self.VLAN_MAC_XLATE_TABLE)
        rm.add_action(Action.GOTO(self.VLAN_CIRCUIT_TABLE))
        rm.add_option(self.DROP_PRIORITY)
        rms.append(rm)

        ## VLAN CIRCUIT Table 3
        # only default drop rule

        ## PRIORITY MAP Table 4
        # Clear actions
        rm = RouteMod(RMT_ADD, self.dp_id)
        rm.set_table(self.PRIORITY_MAP_TABLE)
        rm.add_action(Action.CLEAR_DEFERRED())
        rm.add_option(self.DROP_PRIORITY)
        rms.append(rm)

        ## L3 Interface MAC DA Table 5
        # Allow MAC broadcast frames on all ports
        rm = RouteMod(RMT_ADD, self.dp_id)
        rm.set_table(self.L3_IF_MAC_DA_TABLE)
        rm.add_match(Match.ETHERNET("ff:ff:ff:ff:ff:ff"))
        rm.add_action(Action.GOTO(self.ETHER_TABLE))
        rm.add_option(self.CONTROLLER_PRIORITY)
        rms.append(rm)

        ## Ethertype Table 6
        rm = RouteMod(RMT_ADD, self.dp_id)
        rm.set_table(self.ETHER_TABLE)
        rm.add_match(Match.ETHERTYPE(ETHERTYPE_ARP))
        rm.add_action(Action.CONTROLLER())
        rm.add_option(self.CONTROLLER_PRIORITY)
        rms.append(rm)
        # IPv4
        rm = RouteMod(RMT_ADD, self.dp_id)
        rm.set_table(self.ETHER_TABLE)
        rm.add_match(Match.ETHERTYPE(ETHERTYPE_IP))
        rm.add_action(Action.GOTO(self.FIB_TABLE))
        rm.add_option(self.CONTROLLER_PRIORITY)
        rms.append(rm)

        ## FIB Table 7
        # only default drop rule

        ## Local (destined to router) Table 9
        # For now, allow all protocols to be sent to controller/router
        rm = RouteMod(RMT_ADD, self.dp_id)
        rm.set_table(self.LOCAL_TABLE)
        rm.add_action(Action.CONTROLLER())
        rm.add_option(self.CONTROLLER_PRIORITY)
        rms.append(rm)

        return rms

    def _send_rm_with_matches(self, rm, out_port, entries):
        rms = []
        for entry in entries:
            if out_port != entry.dp_port:
                if (entry.get_status() == RFENTRY_ACTIVE or
                    entry.get_status() == RFISL_ACTIVE):
                    dst_eth = None
                    actions = rm.actions
                    rm.set_actions(None)
                    for action_dict in actions:
                        action = Action.from_dict(action_dict)
                        action_type = action.type_to_str(action._type)
                        if action_type == 'RFAT_SET_ETH_DST':
                            dst_eth = action.get_value()
                        elif action_type == 'RFAT_SWAP_VLAN_ID':
                            vlan_id = action.get_value()
                            action = Action.SET_VLAN_ID(vlan_id | OFPVID_PRESENT)
                        rm.add_action(action)
                    if dst_eth not in self.actions_to_groupid:
                        self.last_groupid += 1
                        new_groupid = self.last_groupid
                        self.actions_to_groupid[dst_eth] = new_groupid
                        group_rm = RouteMod(RMT_ADD_GROUP, self.dp_id)
                        group_rm.set_group(new_groupid)
                        group_rm.set_actions(rm.actions)
                        rms.append(group_rm)
                        self.log.info("adding new group %u for Ethernet destination %s" % (
                            new_groupid, dst_eth))
                    rm.set_actions(None)
                    rm.add_action(Action.GROUP_DEFERRED(self.actions_to_groupid[dst_eth]))
                    rms.append(rm)
                    break
        return rms

    def handle_controller_route_mod(self, entry, rm):
        rms = []
        rm.add_action(Action.GOTO(self.LOCAL_TABLE))
        rm.set_table(self.FIB_TABLE)
        dl_dst = None
        dst_vlan = None
        orig_matches = rm.get_matches()
        rm.set_matches(None)
        for match_dict in orig_matches:
            match = Match.from_dict(match_dict)
            match_type = match.type_to_str(match._type)
            if match_type == "RFMT_ETHERNET":
                dl_dst = match
            # TODO: support more than IP address matches
            # TODO: support more than IPv4
            elif match_type == "RFMT_IPV4":
                rm.add_match(Match.ETHERTYPE(ETHERTYPE_IP))
                rm.add_match(match)
            elif match_type == "RFMT_VLAN_ID":
                dst_vlan = match.get_value()

        if rm.matches:
            rms.append(rm)

        if dst_vlan is not None:
            vlan_rm = RouteMod(RMT_ADD, self.dp_id)
            vlan_rm.set_table(self.VLAN_CIRCUIT_TABLE)
            vlan_rm.add_match(Match.IN_PORT(entry.dp_port))
            vlan_rm.add_match(Match.VLAN_ID(dst_vlan))
            vlan_rm.add_action(Action.SET_VLAN_PCP(7))
            vlan_rm.add_action(Action.SET_QUEUE(0))
            vlan_rm.add_action(Action.APPLY_METER(1))
            vlan_rm.add_action(Action.GOTO(self.L3_IF_MAC_DA_TABLE))
            vlan_rm.add_option(self.CONTROLLER_PRIORITY)
            rms.append(vlan_rm)

        if dl_dst is not None:
            hw_rm = RouteMod(RMT_CONTROLLER, entry.dp_id)
            hw_rm.set_table(self.L3_IF_MAC_DA_TABLE)
            hw_rm.set_id(rm.get_id())
            hw_rm.set_vm_port(rm.get_vm_port())
            hw_rm.add_match(Match.IN_PORT(entry.dp_port))
            hw_rm.add_match(dl_dst)
            hw_rm.add_action(Action.GOTO(self.ETHER_TABLE))
            hw_rm.add_option(self.DEFAULT_PRIORITY)
            rms.append(hw_rm)

        return rms

    def handle_route_mod(self, entry, rm):
        rms = []
        entries = self.rftable.get_entries(dp_id=entry.dp_id,
                                           ct_id=entry.ct_id)
        entries.extend(self.isltable.get_entries(dp_id=entry.dp_id,
                                                 ct_id=entry.ct_id))

        # Replace the VM port with the datapath port
        rm.add_action(Action.OUTPUT(entry.dp_port))

        rm.set_table(self.FIB_TABLE)

        rms.extend(self._send_rm_with_matches(rm, entry.dp_port, entries))
        return rms

class RFServer(RFProtocolFactory, IPC.IPCMessageProcessor):
    VENDOR_CLASSES = {
        "noviflow" : NoviFlowMultitableRouteModTranslator,
        "corsa"    : CorsaMultitableRouteModTranslator_v1,
        "corsa-v1" : CorsaMultitableRouteModTranslator_v1,
        "corsa-v3" : CorsaMultitableRouteModTranslator_v3,
    }

    def __init__(self, configfile, islconffile, multitabledps, satellitedps, fpconf):
        self.config = RFConfig(configfile)
        self.islconf = RFISLConf(islconffile)
        self.fpconf = RFFPConf(fpconf)
        self.labeller = MetaVLAN()

        try:
            # Split out records assuming a format of: "dpid/vendor,dpid/vendor, ..."
            dp_vendor_pairs = [dpv.split("/") for dpv in multitabledps.split(",")]
            # Convert the dpids from strings to ints
            dp_vendor_pairs = map(lambda x: [int(x[0], 16), x[1]], dp_vendor_pairs)
            # Map vendor names to RouteModTranslator subclass to detect config errors early
            dp_vendor_pairs = map(lambda x: [x[0], RFServer.VENDOR_CLASSES[x[1]]], dp_vendor_pairs)
            self.multitabledps = dict(dp_vendor_pairs)
        except (ValueError,IndexError,KeyError):
            print "Error parsing multitabledps list '%s'.  Ignored." % multitabledps
            self.multitabledps = dict()
        try:
            self.satellitedps = set([int(x, 16) for x in satellitedps.split(",")])
        except ValueError:
            self.satellitedps = set()

        # Initialise state tables
        self.rftable = RFTable()
        self.isltable = RFISLTable()

        self.route_mod_translator = {}

        # Logging
        self.log = logging.getLogger("rfserver")

        if self.satellitedps:
            self.log.info("Datapaths that are ISL satellites: %s",
                          list(self.satellitedps))
        if self.multitabledps:
            self.log.info("Datapaths that support multiple tables: %s",
                          list(self.multitabledps))

        if self.fpconf:
            self.log.info("List of fastpath attachments: %s", list(self.fpconf.get_entries_all()))

        # If we have at least one fastpath link we are using fastpath
        if len(self.fpconf.get_entries_all()) > 0:
            self.fpconf.enabled = True
        else:
            self.fpconf.enabled = False

        if self.fpconf.enabled:
            self.log.info("Fastpath is enabled")
        else:
            self.log.info("Fastpath is disabled")
        fp_allocate_labels(self.labeller, self.log, self.config, self.fpconf, self.islconf)

        self.ack_q = Queue.Queue()
        self.dp_q = Queue.Queue()
        self.ipc_lock = threading.Lock()
        self.routemod_outstanding = threading.Event()
        self.ipc = IPCService.for_server(RFSERVER_ID)

        self.worker = threading.Thread(target=self.dp_worker)
        self.worker.daemon = True
        self.worker.start()

        self.ipc.listen(RFCLIENT_RFSERVER_CHANNEL, self, self, False)
        self.ipc.listen(RFSERVER_RFPROXY_CHANNEL, self, self, True)

    def ipc_send(self, channel, channel_id, msg):
        self.ipc_lock.acquire()
        self.ipc.send(channel, channel_id, msg)
        self.ipc_lock.release()
    
    def dp_worker(self):
        while True:
            (ct_id, rm) = self.dp_q.get(block=True)
            self.ipc_send(RFSERVER_RFPROXY_CHANNEL, ct_id, rm)
            self.dp_q.task_done()

    def send_routemod_acks(self):
        while not self.ack_q.empty():
            (vm_id, ack) = self.ack_q.get()
            self.ipc_send(RFCLIENT_RFSERVER_CHANNEL, vm_id, ack)
            self.ack_q.task_done()

    def process(self, from_, to, channel, msg):
        type_ = msg.get_type()
        if channel == RFCLIENT_RFSERVER_CHANNEL:
            if type_ == ROUTE_MOD:
                self.register_route_mod(msg)
            elif type_ == PORT_REGISTER:
                self.register_vm_port(msg.get_vm_id(), msg.get_vm_port(),
                                      msg.get_hwaddress())
        elif channel == RFSERVER_RFPROXY_CHANNEL:
            if type_ == DATAPATH_PORT_REGISTER:
                self.register_dp_port(msg.get_ct_id(),
                                      msg.get_dp_id(),
                                      msg.get_dp_port())
            elif type_ == DATAPATH_DOWN:
                self.set_dp_down(msg.get_ct_id(), msg.get_dp_id())
            elif type_ == VIRTUAL_PLANE_MAP:
                self.map_port(msg.get_vm_id(), msg.get_vm_port(),
                              msg.get_vs_id(), msg.get_vs_port())
            elif type_ == ROUTE_MOD:
                self.send_routemod_acks()

    # Port register methods
    def register_vm_port(self, vm_id, vm_port, eth_addr):
        action = None
        config_entry = self.config.get_config_for_vm_port(vm_id, vm_port)
        if config_entry is None:
            # Register idle VM awaiting for configuration
            action = REGISTER_IDLE
            self.log.warning('No config entry for client port (vm_id=%s, vm_port=%i)'
                % (format_id(vm_id), vm_port))
        else:
            entry = self.rftable.get_entry_by_dp_port(config_entry.ct_id,
                                                      config_entry.dp_id,
                                                      config_entry.dp_port)
            # If there's no entry, we have no DP, register VM as idle
            if entry is None:
                action = REGISTER_IDLE
            # If there's an idle DP entry matching configuration, associate
            elif entry.get_status() == RFENTRY_IDLE_DP_PORT:
                action = REGISTER_ASSOCIATED

        # Apply action
        if action == REGISTER_IDLE:
            self.rftable.set_entry(RFEntry(vm_id=vm_id, vm_port=vm_port,
                                           eth_addr=eth_addr))
            self.log.info("Registering client port as idle (vm_id=%s, "
                          "vm_port=%i, eth_addr=%s)" % (format_id(vm_id),
                                                        vm_port, eth_addr))
        elif action == REGISTER_ASSOCIATED:
            entry.associate(vm_id, vm_port, eth_addr=eth_addr)
            self.rftable.set_entry(entry)
            self.log.info("Registering client port and associating to "
                          "datapath port (vm_id=%s, vm_port=%i, "
                          "eth_addr = %s, dp_id=%s, dp_port=%s)"
                          % (format_id(vm_id), vm_port, eth_addr,
                             format_id(entry.dp_id), entry.dp_port))

    def queue_routemod_ack(self, ct_id, vm_id, vm_port):
        self.ack_q.put((str(vm_id), 
                        PortConfig(vm_id=vm_id, vm_port=vm_port, operation_id=PCT_ROUTEMOD_ACK)))

    def send_route_mod(self, ct_id, rm):
        rm.add_option(Option.CT_ID(ct_id))
        self.dp_q.put((str(ct_id), rm))

    # Handle RouteMod messages (type ROUTE_MOD)
    #
    # Takes a RouteMod, replaces its VM id,port with the associated DP id,port
    # and sends to the corresponding controller
    def register_route_mod(self, rm):
        vm_id = rm.get_id()
        vm_port = rm.get_vm_port()

        # Find the (vmid, vm_port), (dpid, dpport) pair
        entry = self.rftable.get_entry_by_vm_port(vm_id, vm_port)
        translator = self.route_mod_translator[entry.dp_id]

        # If we can't find an associated datapath for this RouteMod,
        # drop it.
        if entry is None or entry.get_status() == RFENTRY_IDLE_VM_PORT:
            self.log.info("Received RouteMod destined for unknown "
                          "datapath - Dropping (vm_id=%s, vm_port=%d)" %
                          (format_id(vm_id), vm_port))
            return

        # Replace the VM id,port with the Datapath id.port
        rm.set_id(int(entry.dp_id))

        rms = []
        
        if rm.get_mod() is RMT_CONTROLLER:
            rms.extend(translator.handle_controller_route_mod(entry, rm))

        elif rm.get_mod() in (RMT_ADD, RMT_DELETE):
            rms.extend(translator.handle_route_mod(entry, rm))

            remote_dps = self.isltable.get_entries(rem_ct=entry.ct_id,
                                                   rem_id=entry.dp_id)

            for r in remote_dps:
                if r.get_status() == RFISL_ACTIVE:
                    local_rm = copy.deepcopy(rm)
                    remote_translator = self.route_mod_translator[int(r.dp_id)]
                    rms.extend(remote_translator.handle_isl_route_mod(r, local_rm))
        else:
            self.log.info("Received RouteMod with unknown type: %s " % rm)

        for rm in rms:
            self.send_route_mod(entry.ct_id, rm)

        self.queue_routemod_ack(entry.ct_id, vm_id, vm_port)

    # DatapathPortRegister methods
    def register_dp_port(self, ct_id, dp_id, dp_port):
        stop = self.config_dp(ct_id, dp_id)
        if stop:
            return

        # The logic down here is pretty much the same as register_vm_port
        action = None
        config_entry = self.config.get_config_for_dp_port(ct_id, dp_id,
                                                          dp_port)
        if config_entry is None:
            islconfs = self.islconf.get_entries_by_port(ct_id, dp_id, dp_port)
            if islconfs:
                action = REGISTER_ISL
            else:
                # Register idle DP awaiting for configuration
                action = REGISTER_IDLE
        else:
            entry = self.rftable.get_entry_by_vm_port(config_entry.vm_id,
                                                      config_entry.vm_port)
            # If there's no entry, we have no VM, register DP as idle
            if entry is None:
                action = REGISTER_IDLE
            # If there's an idle VM entry matching configuration, associate
            elif entry.get_status() == RFENTRY_IDLE_VM_PORT:
                action = REGISTER_ASSOCIATED

        # Apply action
        if action == REGISTER_IDLE:
            self.rftable.set_entry(RFEntry(ct_id=ct_id, dp_id=dp_id,
                                           dp_port=dp_port))
            self.log.info("Registering datapath port as idle (dp_id=%s, "
                          "dp_port=%i)" % (format_id(dp_id), dp_port))
        elif action == REGISTER_ASSOCIATED:
            entry.associate(dp_id, dp_port, ct_id)
            self.rftable.set_entry(entry)
            self.log.info("Registering datapath port and associating to "
                          "client port (dp_id=%s, dp_port=%i, vm_id=%s, "
                          "vm_port=%s)" % (format_id(dp_id), dp_port,
                                           format_id(entry.vm_id),
                                           entry.vm_port))
        elif action == REGISTER_ISL:
            self._register_islconf(islconfs, ct_id, dp_id, dp_port)

    def _register_islconf(self, c_entries, ct_id, dp_id, dp_port):
        for conf in c_entries:
            entry = None
            eth_addr = None
            if conf.rem_id != dp_id or conf.rem_ct != ct_id:
                entry = self.isltable.get_entry_by_addr(conf.rem_ct,
                                                        conf.rem_id,
                                                        conf.rem_port,
                                                        conf.rem_eth_addr)
                eth_addr = conf.eth_addr
            else:
                entry = self.isltable.get_entry_by_addr(conf.ct_id,
                                                        conf.dp_id,
                                                        conf.dp_port,
                                                        conf.eth_addr)
                eth_addr = conf.rem_eth_addr

            if entry is None:
                n_entry = RFISLEntry(vm_id=conf.vm_id, ct_id=ct_id,
                                     dp_id=dp_id, dp_port=dp_port,
                                     eth_addr=eth_addr)
                self.isltable.set_entry(n_entry)
                self.log.info("Registering ISL port as idle "
                              "(dp_id=%s, dp_port=%i, eth_addr=%s)" %
                              (format_id(dp_id), dp_port, eth_addr))
            elif entry.get_status() == RFISL_IDLE_DP_PORT:
                entry.associate(ct_id, dp_id, dp_port, eth_addr)
                self.isltable.set_entry(entry)
                n_entry = self.isltable.get_entry_by_remote(entry.ct_id,
                                                            entry.dp_id,
                                                            entry.dp_port,
                                                            entry.eth_addr)
                if n_entry is None:
                    n_entry = RFISLEntry(vm_id=entry.vm_id, ct_id=ct_id,
                                         dp_id=dp_id, dp_port=dp_port,
                                         eth_addr=entry.rem_eth_addr,
                                         rem_ct=entry.ct_id,
                                         rem_id=entry.dp_id,
                                         rem_port=entry.dp_port,
                                         rem_eth_addr=entry.eth_addr)
                    self.isltable.set_entry(n_entry)
                else:
                    n_entry.associate(ct_id, dp_id, dp_port, eth_addr)
                    self.isltable.set_entry(n_entry)
                self.log.info("Registering ISL port and associating to "
                              "remote ISL port (ct_id=%s, dp_id=%s, "
                              "dp_port=%s, rem_ct=%s, rem_id=%s, "
                              "rem_port=%s)" % (ct_id, format_id(dp_id),
                                                dp_port, entry.ct_id,
                                                format_id(entry.dp_id),
                                                entry.dp_port))

    def send_datapath_config_messages(self, ct_id, dp_id):
        rms = self.route_mod_translator[dp_id].configure_datapath()
        for rm in rms:
            self.send_route_mod(ct_id, rm) 

    def config_dp(self, ct_id, dp_id):
        if is_rfvs(dp_id):
            return True
        else:
            if (self.rftable.is_dp_registered(ct_id, dp_id) or
                self.isltable.is_dp_registered(ct_id, dp_id)):
                if dp_id not in self.route_mod_translator:
                    self.log.info("Configuring datapath (dp_id=%s)" % format_id(dp_id))
                    if dp_id in self.multitabledps:
                        vendor_class = self.multitabledps[dp_id]
                        self.route_mod_translator[dp_id] = vendor_class(
                            dp_id, ct_id, self.rftable, self.isltable, self.config, self.islconf,
                            self.fpconf, self.log, self.labeller)
                    elif dp_id in self.satellitedps:
                        self.route_mod_translator[dp_id] = SatelliteRouteModTranslator(
                            dp_id, ct_id, self.rftable, self.isltable, self.config, self.islconf,
                            self.fpconf, self.log, self.labeller)
                    else:
                        self.route_mod_translator[dp_id] = DefaultRouteModTranslator(
                            dp_id, ct_id, self.rftable, self.isltable, self.config, self.islconf,
                            self.fpconf, self.log, self.labeller)
                    self.send_datapath_config_messages(ct_id, dp_id) 
            return False
    # DatapathDown methods
    def set_dp_down(self, ct_id, dp_id):
        for entry in self.rftable.get_dp_entries(ct_id, dp_id):
            # For every port registered in that datapath, put it down
            self.set_dp_port_down(entry.ct_id, entry.dp_id, entry.dp_port)
        for entry in self.isltable.get_dp_entries(ct_id, dp_id):
            entry.make_idle(RFISL_IDLE_REMOTE)
            self.isltable.set_entry(entry)
        for entry in self.isltable.get_entries(rem_ct=ct_id, rem_id=dp_id):
            entry.make_idle(RFISL_IDLE_DP_PORT)
            self.isltable.set_entry(entry)
        self.log.info("Datapath down (dp_id=%s)" % format_id(dp_id))

    def set_dp_port_down(self, ct_id, dp_id, dp_port):
        entry = self.rftable.get_entry_by_dp_port(ct_id, dp_id, dp_port)
        if entry is not None:
            # If the DP port is registered, delete it and leave only the
            # associated VM port. Reset this VM port so it can be reused.
            vm_id, vm_port = entry.vm_id, entry.vm_port
            entry.make_idle(RFENTRY_IDLE_VM_PORT)
            self.rftable.set_entry(entry)
            if vm_id is not None:
                self.reset_vm_port(vm_id, vm_port)
            self.log.debug("Datapath port down (dp_id=%s, dp_port=%i)" %
                           (format_id(dp_id), dp_port))

    def reset_vm_port(self, vm_id, vm_port):
        if vm_id is None:
            return
        self.ipc_send(RFCLIENT_RFSERVER_CHANNEL, str(vm_id),
                      PortConfig(vm_id=vm_id, vm_port=vm_port,
                                 operation_id=PCT_RESET))
        self.log.info("Resetting client port (vm_id=%s, vm_port=%i)" %
                      (format_id(vm_id), vm_port))

    # PortMap methods
    def map_port(self, vm_id, vm_port, vs_id, vs_port):
        entry = self.rftable.get_entry_by_vm_port(vm_id, vm_port)
        if entry is not None and entry.get_status() == RFENTRY_ASSOCIATED:
            # If the association is valid, activate it
            entry.activate(vs_id, vs_port)
            self.rftable.set_entry(entry)
            msg = DataPlaneMap(ct_id=entry.ct_id,
                               dp_id=entry.dp_id, dp_port=entry.dp_port,
                               vs_id=vs_id, vs_port=vs_port)
            self.ipc_send(RFSERVER_RFPROXY_CHANNEL, str(entry.ct_id), msg)
            msg = PortConfig(vm_id=vm_id, vm_port=vm_port,
                             operation_id=PCT_MAP_SUCCESS)
            self.ipc_send(RFCLIENT_RFSERVER_CHANNEL, str(entry.vm_id), msg)
            self.log.info("Mapping client-datapath association "
                          "(vm_id=%s, vm_port=%i, dp_id=%s, "
                          "dp_port=%i, vs_id=%s, vs_port=%i)" %
                          (format_id(entry.vm_id), entry.vm_port,
                           format_id(entry.dp_id), entry.dp_port,
                           format_id(entry.vs_id), entry.vs_port))

if __name__ == "__main__":
    description = 'RFServer co-ordinates RFClient and RFProxy instances, ' \
                  'listens for route updates, and configures flow tables'
    epilog = 'Report bugs to: https://github.com/routeflow/RouteFlow/issues'

    config = os.path.dirname(os.path.realpath(__file__)) + "/config.csv"
    islconf = os.path.dirname(os.path.realpath(__file__)) + "/islconf.csv"

    parser = argparse.ArgumentParser(description=description, epilog=epilog)
    parser.add_argument('configfile', default=config,
                        help='VM-VS-DP mapping configuration file')
    parser.add_argument('-i', '--islconfig', default=islconf,
                        help='ISL mapping configuration file')
    parser.add_argument('-m', '--multitabledps', default='',
                        help='List of datapaths ("dpid/vendor") that support multiple tables '
                             '[supported vendors: %s]' % RFServer.VENDOR_CLASSES.keys())
    parser.add_argument('-s', '--satellitedps', default='',
                        help='List of datapaths that default forward to ISL peer')
    parser.add_argument('-f', '--fastpaths', default='',
                        help='List of "fastpath" link(s) to the controller')

    args = parser.parse_args()
    server = RFServer(args.configfile, args.islconfig, args.multitabledps, args.satellitedps, args.fastpaths)