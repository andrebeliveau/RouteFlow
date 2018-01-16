from rflib.defs import *
from TLV import *
from bson.binary import Binary

# Band Type Variables ('Enum')
RFBT_DROP = 1
RFBT_DSCP_REMARK = 2
RFBT_EXPERIMENTER = 255

typeStrings = {
            RFBT_DROP : "RFBT_DROP",
            RFBT_DSCP_REMARK : "RFBT_DSCP_REMARK",
            RFBT_EXPERIMENTER : "RFBT_EXPERIMENTER",
        }

class Band(TLV):

    def __init__(self, bandType=None, **fields):
        super(Band, self).__init__(bandType, self.type_to_bin(bandType, fields))

    def __str__(self):
        return "%s : %s" % (self.type_to_str(self._type), self.get_value())

    @classmethod
    def DROP(cls, rate=None, burst_size=None):
        return cls(RFBT_DROP, rate=rate, burst_size=burst_size)

    @classmethod
    def DSCP_REMARK(cls, rate=None, burst_size=None, prec_level=None):
        return cls(RFBT_DSCP_REMARK, rate=rate, burst_size=burst_size,
                   prec_level=prec_level)

    @classmethod
    def EXPERIMENTER(cls, rate=None, burst_size=None, experimenter=None):
        return cls(RFBT_EXPERIMENTER, rate=rate, burst_size=burst_size,
                   experimenter=experimenter)

    @classmethod
    def from_dict(cls, dic):
        ac = cls()
        ac._type = dic['type']
        ac._value = dic['value']
        return ac

    @staticmethod
    def type_to_bin(bandType, fields):
        bin_ = (int_to_bin(fields.get('rate', None) or 0, 32) +
                int_to_bin(fields.get('burst_size', None) or 0, 32))
        if bandType == RFBT_DROP:
            return bin_
        elif bandType == RFBT_DSCP_REMARK:
            return bin_ + int_to_bin(fields.get('prec_level', None) or 0, 8)
        elif bandType == RFBT_EXPERIMENTER:
            return bin_ + int_to_bin(fields.get('experimenter', None) or 0, 32)
        else:
            return None

    @staticmethod
    def type_to_str(bandType):
        if bandType in typeStrings:
            return typeStrings[bandType]
        else:
            return str(bandType)

    def get_value(self):
        fields = {}
        fields['rate'] = bin_to_int(self._value[:4])
        fields['burst_size'] = bin_to_int(self._value[4:8])
        if self._type == RFBT_DSCP_REMARK:
            fields['prec_level'] = bin_to_int(self._value[8:])
        elif self._type == RFBT_EXPERIMENTER:
            fields['experimenter'] = bin_to_int(self._value[8:])
        elif self._type != RFBT_DROP:
            return None
        return fields

    def set_value(self, value):
        self._value = Binary(self.type_to_bin(self._type, value), 0)

    def _get_field(self, name):
        try:
            return self.get_value()[name]
        except KeyError:
            return None

    def _set_field(self, name, value):
        fields = self.get_value()
        fields[name] = value
        self.set_value(fields)

    def get_rate(self):
        return self._get_field('rate')

    def set_rate(self, rate):
        return self._set_field('rate', rate)

    def get_burst_size(self):
        return self._get_field('burst_size')

    def set_burst_size(self, burst_size):
        return self._set_field('burst_size', burst_size)

    def get_prec_level(self):
        return self._get_field('prec_level')

    def set_prec_level(self, prec_level):
        return self._set_field('prec_level', prec_level)

    def get_experimenter(self):
        return self._get_field('experimenter')

    def set_experimenter(self, experimenter):
        return self._set_field('experimenter', experimenter)
