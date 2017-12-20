import pymongo as mongo

from rflib.defs import MONGO_ADDRESS, MONGO_DB_NAME
import rflib.ipc.IPC as IPC

FROM_FIELD = "from"
TO_FIELD = "to"
TYPE_FIELD = "type"
READ_FIELD = "read"
CONTENT_FIELD = "content"

# 1 MB for the capped collection
CC_SIZE = 1048576

def put_in_envelope(from_, to, msg):
    envelope = {}

    envelope[FROM_FIELD] = from_
    envelope[TO_FIELD] = to
    envelope[READ_FIELD] = False
    envelope[TYPE_FIELD] = msg.get_type()

    envelope[CONTENT_FIELD] = {}
    for (k, v) in msg.to_dict().items():
        envelope[CONTENT_FIELD][k] = v

    return envelope

def take_from_envelope(envelope, factory):
    msg = factory.build_for_type(envelope[TYPE_FIELD]);
    msg.from_dict(envelope[CONTENT_FIELD]);
    return msg;

def format_address(address):
    try:
        tmp = address.split(":")
        if len(tmp) == 2:
            return (tmp[0], int(tmp[1]))
        elif len(tmp) == 1:
            return (tmp[0],)
    except:
        raise ValueError, "Invalid address: " + str(address)
            
class MongoIPCMessageService(IPC.IPCMessageService):
    def __init__(self, address, db, id_, threading_):
        """Construct an IPCMessageService

        Args:
            address: designates where the MongoDB instance is running.
            db: is the database name to connect to on MongoDB.
            id_: is an identifier to allow messages to be directed to the
                appropriate recipient.
            threading_: thread management interface, see IPCService.py
        """
        self._db = db
        self.address = format_address(address)
        self._id = id_
        self._producer_connection = mongo.MongoClient(*self.address)
        self._threading = threading_
        
    def listen(self, channel_id, factory, processor, block=True):
        worker = self._threading.Thread(target=self._listen_worker,
                                        args=(channel_id, factory, processor))
        worker.start()
        if block:
            worker.join()
        
    def send(self, channel_id, to, msg):
        self._create_channel(self._producer_connection, channel_id)
        collection = self._producer_connection[self._db][channel_id]
        collection.insert(put_in_envelope(self.get_id(), to, msg))
        return True

    def _listen_worker(self, channel_id, factory, processor):
        connection = mongo.MongoClient(*self.address)
        self._create_channel(connection, channel_id)
        
        collection = connection[self._db][channel_id]
        cursor = collection.find({TO_FIELD: self.get_id(), READ_FIELD: False}, sort=[("_id", mongo.ASCENDING)])

        while True:
            for envelope in cursor:
                msg = take_from_envelope(envelope, factory)
                processor.process(envelope[FROM_FIELD], envelope[TO_FIELD], channel_id, msg);
                collection.update({"_id": envelope["_id"]}, {"$set": {READ_FIELD: True}})
            self._threading.sleep(0.05)
            cursor = collection.find({TO_FIELD: self.get_id(), READ_FIELD: False}, sort=[("_id", mongo.ASCENDING)])
                
    def _create_channel(self, connection, name):
        db = connection[self._db]
        try:
            collection = mongo.collection.Collection(db, name, None, True, capped=True, size=CC_SIZE)
            collection.ensure_index([("_id", mongo.ASCENDING)])
            collection.ensure_index([(TO_FIELD, mongo.ASCENDING)])
        # TODO: improve this catch. It should be more specific, but pymongo
        # behavior doesn't match its documentation, so we are being dirty.
        except:
            pass

def buildIPC(role, id_, threading_):
    return MongoIPCMessageService(MONGO_ADDRESS, MONGO_DB_NAME, id_, threading_)
