from rflib.defs import *
from TLV import *
from bson.binary import Binary

# Action Type Variables ('Enum')
RFAT_OUTPUT = 1         # Output port
RFAT_SET_ETH_SRC = 2    # Ethernet source address
RFAT_SET_ETH_DST = 3    # Ethernet destination address
RFAT_PUSH_MPLS = 4      # Push MPLS label
RFAT_POP_MPLS = 5       # Pop MPLS label
RFAT_SWAP_MPLS = 6      # Swap MPLS label
RFAT_PUSH_VLAN_ID = 7   # Push VLAN ID
RFAT_STRIP_VLAN_DEFERRED = 8 # Strip outermost VLAN (defer in write instructions)
RFAT_SWAP_VLAN_ID = 9   # Pop and swap a VLAN header
RFAT_GROUP = 10         # Output group
RFAT_GOTO = 11          # Goto table
RFAT_CLEAR_DEFERRED = 12 # Apply group (defer in write instructions)
RFAT_SET_VLAN_PCP = 13  # Set VLAN PCP
RFAT_SET_QUEUE = 14     # Set queue
RFAT_APPLY_METER = 15   # Apply meter
RFAT_GROUP_DEFERRED = 16 # Output group (defer in write instructions)
RFAT_SET_VLAN_ID = 17   # Set VLAN ID
RFAT_STRIP_VLAN = 18    # Strip VLAN now
RFAT_DROP = 254         # Drop packet (Unimplemented)
RFAT_SFLOW = 255        # Generate SFlow messages (Unimplemented)

typeStrings = {
            RFAT_OUTPUT : "RFAT_OUTPUT",
            RFAT_SET_ETH_SRC : "RFAT_SET_ETH_SRC",
            RFAT_SET_ETH_DST : "RFAT_SET_ETH_DST",
            RFAT_PUSH_MPLS : "RFAT_PUSH_MPLS",
            RFAT_POP_MPLS : "RFAT_POP_MPLS",
            RFAT_SWAP_MPLS : "RFAT_SWAP_MPLS",
            RFAT_PUSH_VLAN_ID : "RFAT_PUSH_VLAN_ID",
            RFAT_STRIP_VLAN_DEFERRED : "RFAT_STRIP_VLAN_DEFERRED",
            RFAT_SWAP_VLAN_ID : "RFAT_SWAP_VLAN_ID",
            RFAT_GROUP : "RFAT_GROUP",
            RFAT_GOTO : "RFAT_GOTO",
            RFAT_CLEAR_DEFERRED : "RFAT_CLEAR_DEFERRED",
            RFAT_SET_VLAN_PCP : "RFAT_SET_VLAN_PCP",
            RFAT_SET_QUEUE : "RFAT_SET_QUEUE",
            RFAT_APPLY_METER : "RFAT_APPLY_METER",
            RFAT_GROUP_DEFERRED : "RFAT_GROUP_DEFERRED",
            RFAT_SET_VLAN_ID : "RFAT_SET_VLAN_ID",
        }

ACTION_BIN = (
  RFAT_OUTPUT,
  RFAT_PUSH_MPLS,
  RFAT_SWAP_MPLS,
  RFAT_PUSH_VLAN_ID,
  RFAT_SWAP_VLAN_ID,
  RFAT_GROUP,
  RFAT_GOTO,
  RFAT_SET_VLAN_PCP,
  RFAT_SET_QUEUE,
  RFAT_APPLY_METER,
  RFAT_GROUP_DEFERRED,
  RFAT_SET_VLAN_ID,
)

class Action(TLV):

    def __init__(self, actionType=None, value=None):
        super(Action, self).__init__(actionType, self.type_to_bin(actionType, value))

    def __str__(self):
        return "%s : %s" % (self.type_to_str(self._type), self.get_value())

    @classmethod
    def OUTPUT(cls, port):
        return cls(RFAT_OUTPUT, port)

    @classmethod
    def SET_ETH_SRC(cls, ethernet_src):
        return cls(RFAT_SET_ETH_SRC, ethernet_src)

    @classmethod
    def SET_ETH_DST(cls, ethernet_dst):
        return cls(RFAT_SET_ETH_DST, ethernet_dst)

    @classmethod
    def PUSH_MPLS(cls, label):
        return cls(RFAT_PUSH_MPLS, label)

    @classmethod
    def POP_MPLS(cls):
        return cls(RFAT_POP_MPLS, None)

    @classmethod
    def SWAP_MPLS(cls, label):
        return cls(RFAT_SWAP_MPLS, label)

    @classmethod
    def PUSH_VLAN_ID(cls, vlan_id):
        return cls(RFAT_PUSH_VLAN_ID, vlan_id)

    @classmethod
    def SWAP_VLAN_ID(cls, vlan_id):
        return cls(RFAT_SWAP_VLAN_ID, vlan_id)

    @classmethod
    def DROP(cls):
        return cls(RFAT_DROP, None)

    @classmethod
    def POP_SFLOW(cls):
        return cls(RFAT_POP_SFLOW, None)

    @classmethod
    def CONTROLLER(cls):
        return cls(RFAT_OUTPUT, OFPP_CONTROLLER)

    @classmethod
    def GROUP(cls, group):
        return cls(RFAT_GROUP, group)

    @classmethod
    def GOTO(cls, table):
        return cls(RFAT_GOTO, table)

    @classmethod
    def STRIP_VLAN_DEFERRED(cls):
        return cls(RFAT_STRIP_VLAN_DEFERRED)

    @classmethod
    def STRIP_VLAN(cls):
        return cls(RFAT_STRIP_VLAN)

    @classmethod
    def CLEAR_DEFERRED(cls):
        return cls(RFAT_CLEAR_DEFERRED, None)

    @classmethod
    def SET_VLAN_PCP(cls, vlan_pcp):
        return cls(RFAT_SET_VLAN_PCP, vlan_pcp)

    @classmethod
    def SET_QUEUE(cls, queue):
        return cls(RFAT_SET_QUEUE, queue)

    @classmethod
    def APPLY_METER(cls, meter_id):
        return cls(RFAT_APPLY_METER, meter_id)

    @classmethod
    def GROUP_DEFERRED(cls, group):
        return cls(RFAT_GROUP_DEFERRED, group)

    @classmethod
    def SET_VLAN_ID(cls, vlan_id):
        return cls(RFAT_SET_VLAN_ID, vlan_id)

    @classmethod
    def from_dict(cls, dic):
        ac = cls()
        ac._type = dic['type']
        ac._value = dic['value']
        return ac

    @staticmethod
    def type_to_bin(actionType, value):
        if actionType in ACTION_BIN:
            return int_to_bin(value, 32)
        elif actionType in (RFAT_SET_ETH_SRC, RFAT_SET_ETH_DST):
            return ether_to_bin(value)
        elif actionType in (RFAT_POP_MPLS, RFAT_DROP, RFAT_SFLOW, RFAT_STRIP_VLAN_DEFERRED, RFAT_STRIP_VLAN, RFAT_CLEAR_DEFERRED):
            return ''
        else:
            return None

    @staticmethod
    def type_to_str(actionType):
        if actionType in typeStrings:
            return typeStrings[actionType]
        else:
            return str(actionType)

    def get_value(self):
        if self._type in ACTION_BIN:
            return bin_to_int(self._value)
        elif self._type in (RFAT_SET_ETH_SRC, RFAT_SET_ETH_DST):
            return bin_to_ether(self._value)
        elif self._type in (RFAT_POP_MPLS, RFAT_DROP, RFAT_SFLOW, RFAT_STRIP_VLAN_DEFERRED, RFAT_STRIP_VLAN, RFAT_CLEAR_DEFERRED):
            return None
        else:
            return None

    def set_value(self, value):
        self._value = Binary(self.type_to_bin(self._type, value), 0)