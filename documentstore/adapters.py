import pymongo

from . import interfaces
from . import exceptions
from . import domain


class MongoDB:
    def __init__(self, uri, dbname="document-store"):
        self._client = pymongo.MongoClient(uri)
        self._dbname = dbname

    def _db(self):
        return self._client[self._dbname]

    def _collection(self, colname):
        return self._db()[colname]

    @property
    def documents(self):
        return self._collection("documents")

    @property
    def documents_bundles(self):
        return self._collection("documents_bundles")

    @property
    def journals(self):
        return self._collection("journals")

    @property
    def changes(self):
        return self._collection("changes")

    def create_indexes(self):
        self.changes.create_index([("timestamp", pymongo.ASCENDING)], background=False)


class Session(interfaces.Session):
    def __init__(self, mongodb_client):
        self._mongodb_client = mongodb_client

    @property
    def documents(self):
        return DocumentStore(self._mongodb_client.documents)

    @property
    def documents_bundles(self):
        return DocumentsBundleStore(self._mongodb_client.documents_bundles)

    @property
    def journals(self):
        return JournalStore(self._mongodb_client.journals)

    @property
    def changes(self):
        return ChangesStore(self._mongodb_client.changes)


class BaseStore(interfaces.DataStore):
    def __init__(self, collection):
        self._collection = collection

    def add(self, data) -> None:
        _manifest = data.manifest
        if not _manifest.get("_id"):
            _manifest["_id"] = data.id()
        try:
            self._collection.insert_one(_manifest)
        except pymongo.errors.DuplicateKeyError:
            raise exceptions.AlreadyExists(
                "cannot add data with id " '"%s": the id is already in use' % data.id()
            ) from None

    def update(self, data) -> None:
        _manifest = data.manifest
        if not _manifest.get("_id"):
            _manifest["_id"] = data.id()
        result = self._collection.replace_one({"_id": _manifest["_id"]}, _manifest)
        if result.matched_count == 0:
            raise exceptions.DoesNotExist(
                "cannot update data with id " '"%s": data does not exist' % data.id()
            )

    def fetch(self, id: str):
        manifest = self._collection.find_one({"_id": id})
        if manifest:
            return self.DomainClass(manifest=manifest)
        else:
            raise exceptions.DoesNotExist(
                "cannot fetch data with id " '"%s": data does not exist' % id
            )


class ChangesStore(interfaces.ChangesDataStore):
    def __init__(self, collection):
        self._collection = collection

    def add(self, change: dict):
        assert "_id" not in change
        assert "timestamp" in change
        self._collection.insert_one(change)

    def filter(self, since: str = "", limit: int = 500):
        return self._collection.find(
            {"timestamp": {"$gte": since}},
            sort=[("timestamp", pymongo.ASCENDING)],
            projection={"_id": False},
        ).limit(limit)


class DocumentStore(BaseStore):
    DomainClass = domain.Document


class DocumentsBundleStore(BaseStore):
    DomainClass = domain.DocumentsBundle


class JournalStore(BaseStore):
    DomainClass = domain.Journal
