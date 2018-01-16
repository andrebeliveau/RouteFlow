#ifndef __BAND_HH__
#define __BAND_HH__

#include "TLV.hh"

enum BandType {
    RFBT_DROP = 1,
    RFBT_DSCP_REMARK = 2,
    RFBT_EXPERIMENTER = 255,
};

class Band : public TLV {
    public:
        Band(const Band& other);
        Band(BandType, boost::shared_array<uint8_t> value);

        Band& operator=(const Band& other);
        bool operator==(const Band& other);
        virtual std::string type_to_string() const;
        virtual mongo::BSONObj to_BSON() const;

        static Band* from_BSON(mongo::BSONObj);
    private:
        static size_t type_to_length(uint8_t);
        static byte_order type_to_byte_order(uint8_t);
};

namespace BandList {
    mongo::BSONArray to_BSON(const std::vector<Band> list);
    std::vector<Band> to_vector(std::vector<mongo::BSONElement> array);
}

#endif /* __BAND_HH__ */
