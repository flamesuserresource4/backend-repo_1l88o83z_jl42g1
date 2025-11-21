import os
from datetime import datetime
from typing import Any, Dict, List, Optional

# Try to import pymongo; if not available at runtime, we'll fall back to in-memory
try:
    from pymongo import MongoClient
    from pymongo.collection import Collection
    from bson import ObjectId
except Exception:  # pragma: no cover
    MongoClient = None  # type: ignore
    Collection = None  # type: ignore
    ObjectId = None  # type: ignore

DATABASE_URL = os.getenv("DATABASE_URL") or "mongodb://localhost:27017"
DATABASE_NAME = os.getenv("DATABASE_NAME") or "appdb"

USE_MEMORY = False
_client = None
_db = None

# -------- In-memory fallback implementation ---------
class _MemoryCollection:
    def __init__(self):
        self.items: Dict[str, Dict[str, Any]] = {}

    def insert_one(self, doc: Dict[str, Any]):
        oid = os.urandom(12).hex()
        self.items[oid] = {**doc, "_id": oid}
        class Res:  # simple result shim
            inserted_id = oid
        return Res()

    def find(self, filter_dict: Dict[str, Any]):
        # very simple filter (only supports _id equals)
        if not filter_dict:
            return list(self.items.values())
        if "_id" in filter_dict:
            val = filter_dict["_id"]
            if isinstance(val, dict) and "$in" in val:
                return [self.items[i] for i in val["$in"] if i in self.items]
            if val in self.items:
                return [self.items[val]]
            return []
        # naive fallback: return all
        return list(self.items.values())

    def update_one(self, filter_dict: Dict[str, Any], update: Dict[str, Any]):
        target_id = filter_dict.get("_id")
        class Res:
            matched_count = 0
            modified_count = 0
        res = Res()
        if target_id in self.items:
            res.matched_count = 1
            if "$inc" in update:
                for k, v in update["$inc"].items():
                    self.items[target_id][k] = int(self.items[target_id].get(k, 0)) + int(v)
            if "$push" in update:
                for k, v in update["$push"].items():
                    arr = self.items[target_id].setdefault(k, [])
                    if isinstance(arr, list):
                        arr.append(v)
            if "$set" in update:
                for k, v in update["$set"].items():
                    self.items[target_id][k] = v
            res.modified_count = 1
        return res

    def find_one(self, filter_dict: Dict[str, Any]):
        items = self.find(filter_dict)
        return items[0] if items else None

    def estimated_document_count(self):
        return len(self.items)

    def delete_one(self, filter_dict: Dict[str, Any]):
        tid = filter_dict.get("_id")
        class Res:
            deleted_count = 0
        res = Res()
        if tid in self.items:
            del self.items[tid]
            res.deleted_count = 1
        return res

class _MemoryDB:
    def __init__(self):
        self._cols: Dict[str, _MemoryCollection] = {}
    def __getattr__(self, name: str) -> _MemoryCollection:
        if name not in self._cols:
            self._cols[name] = _MemoryCollection()
        return self._cols[name]

# -------- Utility serialization ---------

def _serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
    if not doc:
        return doc
    result: Dict[str, Any] = {}
    for k, v in doc.items():
        try:
            from bson import ObjectId as _OID  # type: ignore
            if isinstance(v, _OID):
                result[k] = str(v)
                continue
        except Exception:
            pass
        if isinstance(v, datetime):
            result[k] = v
        elif isinstance(v, list):
            result[k] = [str(x) if _is_object_id(x) else x for x in v]
        elif isinstance(v, dict):
            result[k] = _serialize(v)
        else:
            result[k] = v
    return result


def _is_object_id(val: Any) -> bool:
    try:
        from bson import ObjectId as _OID  # type: ignore
        return isinstance(val, _OID)
    except Exception:
        return False

# -------- Initialize DB (with graceful fallback) ---------
try:
    if MongoClient is None:
        raise RuntimeError("pymongo unavailable")
    _client = MongoClient(DATABASE_URL, serverSelectionTimeoutMS=1500)
    _db = _client[DATABASE_NAME]
    # trigger server selection
    _client.admin.command('ping')
    db = _db  # type: ignore
    _BACKING = "mongo"
except Exception:
    USE_MEMORY = True
    db = _MemoryDB()  # type: ignore
    _BACKING = "memory"

# -------- CRUD Helpers expected by app ---------

def create_document(collection_name: str, data: Dict[str, Any]):
    col = getattr(db, collection_name)
    now = datetime.utcnow()
    payload = {**data}
    payload.setdefault("created_at", now)
    payload.setdefault("updated_at", now)
    res = col.insert_one(payload)
    return getattr(res, "inserted_id", None)


def get_documents(collection_name: str, filter_dict: Dict[str, Any], limit: int = 100) -> List[Dict[str, Any]]:
    col = getattr(db, collection_name)
    f = dict(filter_dict)
    # Convert string id to ObjectId if on mongo
    if not USE_MEMORY and f.get("_id") and isinstance(f["_id"], str):
        try:
            from bson import ObjectId as _OID
            f["_id"] = _OID(f["_id"])
        except Exception:
            pass
    try:
        cursor = col.find(f)
        docs = list(cursor)[: limit]
    except TypeError:
        # memory collection returns list
        docs = col.find(f)[: limit]
    return [_serialize(doc) for doc in docs]


def update_document(collection_name: str, filter_dict: Dict[str, Any], data: Dict[str, Any]) -> int:
    col = getattr(db, collection_name)
    f = dict(filter_dict)
    if not USE_MEMORY and f.get("_id") and isinstance(f["_id"], str):
        try:
            from bson import ObjectId as _OID
            f["_id"] = _OID(f["_id"])
        except Exception:
            pass
    payload = {**data, "updated_at": datetime.utcnow()}
    res = col.update_one(f, {"$set": payload})
    return getattr(res, "modified_count", 0)


def delete_document(collection_name: str, filter_dict: Dict[str, Any]) -> int:
    col = getattr(db, collection_name)
    f = dict(filter_dict)
    if not USE_MEMORY and f.get("_id") and isinstance(f["_id"], str):
        try:
            from bson import ObjectId as _OID
            f["_id"] = _OID(f["_id"])
        except Exception:
            pass
    res = col.delete_one(f)
    return getattr(res, "deleted_count", 0)
