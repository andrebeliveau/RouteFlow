#include <boost/scoped_array.hpp>

#include "Band.hh"

Band::Band(const Band& other) : TLV(other) { }

Band::Band(BandType type, boost::shared_array<uint8_t> value)
    : TLV(type, type_to_length(type), value) { }

Band& Band::operator=(const Band& other) {
    if (this != &other) {
        this->init(other.getType(), other.getLength(), other.getValue());
    }
    return *this;
}

bool Band::operator==(const Band& other) {
    return (this->getType() == other.getType() and
            (memcmp(other.getValue(), this->getValue(), this->length) == 0));
}

std::string Band::type_to_string() const {
    switch (this->type) {
        case RFBT_DROP:             return "RFBT_DROP";
        case RFBT_DSCP_REMARK:      return "RFBT_DSCP_REMARK";
        case RFBT_EXPERIMENTER:     return "RFBT_EXPERIMENTER";
        default:                    return "UNKNOWN_ACTION";
    }
}

size_t Band::type_to_length(uint8_t type) {
    size_t length = sizeof(uint32_t) * 2;
    switch (type) {
        case RFBT_DROP:
            return length;
        case RFBT_DSCP_REMARK:
            return length + sizeof(uint8_t);
        case RFBT_EXPERIMENTER:
            return length + sizeof(uint32_t);
    }
}

/**
 * Determine what byte-order the type is stored in internally
 */
byte_order Band::type_to_byte_order(uint8_t type) {
    return ORDER_HOST;
}

mongo::BSONObj Band::to_BSON() const {
    byte_order order = type_to_byte_order(type);
    return TLV::TLV_to_BSON(this, order);
}


/**
 * Constructs a new TLV object based on the given BSONObj. Converts values
 * formatted in network byte-order to host byte-order.
 *
 * It is the caller's responsibility to free the returned object. If the given
 * BSONObj is not a valid TLV, this method returns NULL.
 */
Band* Band::from_BSON(const mongo::BSONObj bson) {
    BandType type = (BandType)TLV::type_from_BSON(bson);
    if (type == 0)
        return NULL;

    byte_order order = type_to_byte_order(type);
    boost::shared_array<uint8_t> value = TLV::value_from_BSON(bson, order);

    if (value.get() == NULL)
        return NULL;

    return new Band(type, value);
}

namespace BandList {
    mongo::BSONArray to_BSON(const std::vector<Band> list) {
        std::vector<Band>::const_iterator iter;
        mongo::BSONArrayBuilder builder;

        for (iter = list.begin(); iter != list.end(); ++iter) {
            builder.append(iter->to_BSON());
        }

        return builder.arr();
    }

    /**
     * Returns a vector of Bands extracted from 'bson'. 'bson' should be an
     * array of bson-encoded Band objects formatted as follows:
     * [{
     *   "type": (int),
     *   "value": (binary)
     * },
     * ...]
     *
     * If the given 'bson' is not an array, the returned vector will be empty.
     * If any actions in the array are invalid, they will not be added to the
     * vector.
     */
    std::vector<Band> to_vector(std::vector<mongo::BSONElement> array) {
        std::vector<mongo::BSONElement>::iterator iter;
        std::vector<Band> list;

        for (iter = array.begin(); iter != array.end(); ++iter) {
            Band* action = Band::from_BSON(iter->Obj());

            if (action != NULL) {
                list.push_back(*action);
            }
        }

        return list;
    }
}
