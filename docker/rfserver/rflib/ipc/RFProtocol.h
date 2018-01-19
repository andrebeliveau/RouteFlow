#ifndef __RFPROTOCOL_H__
#define __RFPROTOCOL_H__

#include <stdint.h>

#include "converter.h"
#include "ipc/IPC.h"
#include "types/IPAddress.h"
#include "types/MACAddress.h"
#include "types/Action.hh"
#include "types/Match.hh"
#include "types/Option.hh"
#include "types/Band.hh"

enum {
	PORT_REGISTER,
	PORT_CONFIG,
	DATAPATH_PORT_REGISTER,
	DATAPATH_DOWN,
	VIRTUAL_PLANE_MAP,
	DATA_PLANE_MAP,
	ROUTE_MOD
};

class PortRegister : public IPCMessage {
    public:
        PortRegister();
        PortRegister(uint64_t vm_id, uint32_t vm_port, MACAddress hwaddress);

        uint64_t get_vm_id();
        void set_vm_id(uint64_t vm_id);

        uint32_t get_vm_port();
        void set_vm_port(uint32_t vm_port);

        MACAddress get_hwaddress();
        void set_hwaddress(MACAddress hwaddress);

        virtual int get_type();
        virtual void from_BSON(const char* data);
        virtual const char* to_BSON();
        virtual string str();

    private:
        uint64_t vm_id;
        uint32_t vm_port;
        MACAddress hwaddress;
};

class PortConfig : public IPCMessage {
    public:
        PortConfig();
        PortConfig(uint64_t vm_id, uint32_t vm_port, uint32_t operation_id);

        uint64_t get_vm_id();
        void set_vm_id(uint64_t vm_id);

        uint32_t get_vm_port();
        void set_vm_port(uint32_t vm_port);

        uint32_t get_operation_id();
        void set_operation_id(uint32_t operation_id);

        virtual int get_type();
        virtual void from_BSON(const char* data);
        virtual const char* to_BSON();
        virtual string str();

    private:
        uint64_t vm_id;
        uint32_t vm_port;
        uint32_t operation_id;
};

class DatapathPortRegister : public IPCMessage {
    public:
        DatapathPortRegister();
        DatapathPortRegister(uint64_t ct_id, uint64_t dp_id, uint32_t dp_port);

        uint64_t get_ct_id();
        void set_ct_id(uint64_t ct_id);

        uint64_t get_dp_id();
        void set_dp_id(uint64_t dp_id);

        uint32_t get_dp_port();
        void set_dp_port(uint32_t dp_port);

        virtual int get_type();
        virtual void from_BSON(const char* data);
        virtual const char* to_BSON();
        virtual string str();

    private:
        uint64_t ct_id;
        uint64_t dp_id;
        uint32_t dp_port;
};

class DatapathDown : public IPCMessage {
    public:
        DatapathDown();
        DatapathDown(uint64_t ct_id, uint64_t dp_id);

        uint64_t get_ct_id();
        void set_ct_id(uint64_t ct_id);

        uint64_t get_dp_id();
        void set_dp_id(uint64_t dp_id);

        virtual int get_type();
        virtual void from_BSON(const char* data);
        virtual const char* to_BSON();
        virtual string str();

    private:
        uint64_t ct_id;
        uint64_t dp_id;
};

class VirtualPlaneMap : public IPCMessage {
    public:
        VirtualPlaneMap();
        VirtualPlaneMap(uint64_t vm_id, uint32_t vm_port, uint64_t vs_id, uint32_t vs_port);

        uint64_t get_vm_id();
        void set_vm_id(uint64_t vm_id);

        uint32_t get_vm_port();
        void set_vm_port(uint32_t vm_port);

        uint64_t get_vs_id();
        void set_vs_id(uint64_t vs_id);

        uint32_t get_vs_port();
        void set_vs_port(uint32_t vs_port);

        virtual int get_type();
        virtual void from_BSON(const char* data);
        virtual const char* to_BSON();
        virtual string str();

    private:
        uint64_t vm_id;
        uint32_t vm_port;
        uint64_t vs_id;
        uint32_t vs_port;
};

class DataPlaneMap : public IPCMessage {
    public:
        DataPlaneMap();
        DataPlaneMap(uint64_t ct_id, uint64_t dp_id, uint32_t dp_port, uint64_t vs_id, uint32_t vs_port);

        uint64_t get_ct_id();
        void set_ct_id(uint64_t ct_id);

        uint64_t get_dp_id();
        void set_dp_id(uint64_t dp_id);

        uint32_t get_dp_port();
        void set_dp_port(uint32_t dp_port);

        uint64_t get_vs_id();
        void set_vs_id(uint64_t vs_id);

        uint32_t get_vs_port();
        void set_vs_port(uint32_t vs_port);

        virtual int get_type();
        virtual void from_BSON(const char* data);
        virtual const char* to_BSON();
        virtual string str();

    private:
        uint64_t ct_id;
        uint64_t dp_id;
        uint32_t dp_port;
        uint64_t vs_id;
        uint32_t vs_port;
};

class RouteMod : public IPCMessage {
    public:
        RouteMod();
        RouteMod(uint8_t mod, uint64_t id, uint64_t vm_port, uint64_t table, uint64_t group, uint64_t meter,
                 uint64_t flags, std::vector<Match> matches, std::vector<Action> actions,
                 std::vector<Option> options, std::vector<Band> bands);

        uint8_t get_mod();
        void set_mod(uint8_t mod);

        uint64_t get_id();
        void set_id(uint64_t id);

        uint64_t get_vm_port();
        void set_vm_port(uint64_t vm_port);

        uint64_t get_table();
        void set_table(uint64_t table);

        uint64_t get_group();
        void set_group(uint64_t group);

        uint64_t get_meter();
        void set_meter(uint64_t meter);

        uint64_t get_flags();
        void set_flags(uint64_t flags);

        std::vector<Match> get_matches();
        void set_matches(std::vector<Match> matches);
        void add_match(const Match& match);

        std::vector<Action> get_actions();
        void set_actions(std::vector<Action> actions);
        void add_action(const Action& action);

        std::vector<Option> get_options();
        void set_options(std::vector<Option> options);
        void add_option(const Option& option);

        std::vector<Band> get_bands();
        void set_bands(std::vector<Band> bands);
        void add_band(const Band& band);

        virtual int get_type();
        virtual void from_BSON(const char* data);
        virtual const char* to_BSON();
        virtual string str();

    private:
        uint8_t mod;
        uint64_t id;
        uint64_t vm_port;
        uint64_t table;
        uint64_t group;
        uint64_t meter;
        uint64_t flags;
        std::vector<Match> matches;
        std::vector<Action> actions;
        std::vector<Option> options;
        std::vector<Band> bands;
};

#endif /* __RFPROTOCOL_H__ */