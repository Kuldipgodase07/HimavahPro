"""MongoDB Atlas integration layer for HimavahPro.

Connects to MongoDB Atlas, manages collection schemas and indexes,
synchronizes initial data and captures all real-time changes.
"""
from __future__ import annotations

import datetime
import logging
import re
import urllib.parse
from typing import Any

from pymongo import MongoClient, ReplaceOne, IndexModel, ASCENDING, DESCENDING
from pymongo.database import Database
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from . import config

logger = logging.getLogger("himavahpro.mongodb")

_client: MongoClient | None = None
_db: Database | None = None


def clean_mongo_url(raw: str, default_db: str = "himavahpro") -> str:
    """Sanitize MongoDB URI, stripping angle brackets and URL-encoding credentials."""
    s = raw.strip()
    m = re.match(r"^(mongodb(?:\+srv)?://)([^:]+):(.*)@([^/?]+)(?:/([^?]*))?(.*)$", s)
    if not m:
        return s
    proto, user, pwd, host, db, query = m.groups()
    user = user.strip("<>")
    pwd = pwd.strip("<>")
    user = urllib.parse.quote_plus(urllib.parse.unquote_plus(user))
    pwd = urllib.parse.quote_plus(urllib.parse.unquote_plus(pwd))
    db_name = db if db else default_db
    q = query if query else "?retryWrites=true&w=majority"
    if not q.startswith("?"):
        q = "?" + q
    return f"{proto}{user}:{pwd}@{host}/{db_name}{q}"


def get_mongo_client() -> MongoClient | None:
    """Returns singleton MongoClient instance or None if disabled/unreachable."""
    global _client
    if not config.MONGODB_SYNC_ENABLED or not config.MONGODB_URL:
        return None
    if _client is None:
        try:
            uri = clean_mongo_url(config.MONGODB_URL, config.MONGODB_DB_NAME)
            _client = MongoClient(uri, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000)
            # Verify connectivity
            _client.admin.command("ping")
            logger.info("Successfully connected to MongoDB Atlas.")
        except Exception as e:
            logger.warning(f"Could not connect to MongoDB Atlas: {e}")
            _client = None
    return _client


def get_mongo_db() -> Database | None:
    """Returns the application database instance on MongoDB Atlas."""
    global _db
    client = get_mongo_client()
    if client is None:
        return None
    if _db is None:
        _db = client.get_database(config.MONGODB_DB_NAME)
    return _db


def ensure_mongo_schema() -> None:
    """Ensure all required collections and indexes exist in MongoDB Atlas."""
    db = get_mongo_db()
    if db is None:
        return

    indexes: dict[str, list[IndexModel]] = {
        "users": [
            IndexModel([("username", ASCENDING)], unique=True),
            IndexModel([("role", ASCENDING)]),
        ],
        "nodes": [
            IndexModel([("id", ASCENDING)], unique=True),
            IndexModel([("kind", ASCENDING)]),
            IndexModel([("tier", ASCENDING)]),
        ],
        "routes": [
            IndexModel([("id", ASCENDING)], unique=True),
            IndexModel([("a", ASCENDING), ("b", ASCENDING)]),
            IndexModel([("status", ASCENDING)]),
        ],
        "inventory": [
            IndexModel([("post_id", ASCENDING), ("supply_class", ASCENDING)], unique=True),
            IndexModel([("post_id", ASCENDING)]),
            IndexModel([("supply_class", ASCENDING)]),
        ],
        "consumption": [
            IndexModel([("post_id", ASCENDING), ("supply_class", ASCENDING), ("day", ASCENDING)]),
            IndexModel([("day", DESCENDING)]),
        ],
        "movements": [
            IndexModel([("post_id", ASCENDING), ("ts", DESCENDING)]),
            IndexModel([("ts", DESCENDING)]),
        ],
        "recommendations": [
            IndexModel([("id", ASCENDING)], unique=True),
            IndexModel([("post_id", ASCENDING)]),
            IndexModel([("status", ASCENDING)]),
            IndexModel([("created_at", DESCENDING)]),
        ],
        "decisions": [
            IndexModel([("rec_id", ASCENDING), ("ts", DESCENDING)]),
            IndexModel([("ts", DESCENDING)]),
        ],
        "convoys": [
            IndexModel([("id", ASCENDING)], unique=True),
            IndexModel([("dest_post", ASCENDING)]),
            IndexModel([("status", ASCENDING)]),
        ],
        "field_reports": [
            IndexModel([("client_id", ASCENDING)], unique=True, sparse=True),
            IndexModel([("post_id", ASCENDING)]),
            IndexModel([("ts", DESCENDING)]),
        ],
        "sensors": [
            IndexModel([("id", ASCENDING)], unique=True),
            IndexModel([("post_id", ASCENDING)]),
        ],
        "audit_events": [
            IndexModel([("id", ASCENDING)], unique=True),
            IndexModel([("hash", ASCENDING)]),
            IndexModel([("ts", DESCENDING)]),
            IndexModel([("actor", ASCENDING)]),
        ],
        "scenario_runs": [
            IndexModel([("id", ASCENDING)], unique=True),
            IndexModel([("ts", DESCENDING)]),
        ],
        "docs": [
            IndexModel([("key", ASCENDING)], unique=True),
        ],
    }

    for col_name, idx_list in indexes.items():
        try:
            col = db[col_name]
            col.create_indexes(idx_list)
        except Exception as e:
            logger.warning(f"Error creating indexes for MongoDB collection '{col_name}': {e}")


def _serialize_row(row_dict: dict[str, Any]) -> dict[str, Any]:
    """Serialize datetime and other complex types for MongoDB storage."""
    out = {}
    for k, v in row_dict.items():
        if isinstance(v, (datetime.datetime, datetime.date)):
            out[k] = v.isoformat() + "Z"
        else:
            out[k] = v
    return out


def sync_all_to_mongo(session: Session) -> dict[str, int]:
    """Bulk synchronizes all tables and entries from relational session to MongoDB Atlas."""
    from .db import Base

    db = get_mongo_db()
    if db is None:
        return {}

    ensure_mongo_schema()
    counts = {}

    for table_name, table in Base.metadata.tables.items():
        try:
            rows = session.execute(table.select()).mappings().all()
            col = db[table_name]
            pk_cols = [c.name for c in table.primary_key.columns]

            ops = []
            for r in rows:
                doc = _serialize_row(dict(r))
                if len(pk_cols) == 1:
                    pk_val = doc[pk_cols[0]]
                    doc["_id"] = pk_val
                    filter_q = {"_id": pk_val}
                else:
                    filter_q = {pk: doc[pk] for pk in pk_cols}

                ops.append(ReplaceOne(filter_q, doc, upsert=True))

            if ops:
                col.bulk_write(ops, ordered=False)
            counts[table_name] = len(rows)
        except Exception as e:
            logger.warning(f"Failed syncing table {table_name} to MongoDB: {e}")

    logger.info(f"MongoDB Atlas synchronized {sum(counts.values())} records across {len(counts)} collections.")
    return counts


def _instance_to_doc(instance: Any) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Converts a SQLAlchemy instance to collection name, filter query, and document."""
    insp = inspect(instance)
    table_name = insp.mapper.local_table.name
    pk_cols = [c.name for c in insp.mapper.local_table.primary_key.columns]

    doc = {}
    filter_q = {}
    for c in insp.mapper.local_table.columns:
        val = getattr(instance, c.name, None)
        if isinstance(val, (datetime.datetime, datetime.date)):
            val = val.isoformat() + "Z"
        doc[c.name] = val

    if len(pk_cols) == 1:
        pk_val = doc[pk_cols[0]]
        doc["_id"] = pk_val
        filter_q = {"_id": pk_val}
    else:
        filter_q = {pk: doc[pk] for pk in pk_cols}

    return table_name, filter_q, doc


def register_sqlalchemy_mongo_hooks(session_factory: Any) -> None:
    """Registers SQLAlchemy Session flush event listener to mirror all writes to MongoDB Atlas."""

    @event.listens_for(session_factory, "after_flush")
    def after_flush(session: Session, flush_context: Any) -> None:
        if not config.MONGODB_SYNC_ENABLED:
            return
        db = get_mongo_db()
        if db is None:
            return

        # Handle inserts and updates
        for instance in list(session.new) + list(session.dirty):
            try:
                table_name, filter_q, doc = _instance_to_doc(instance)
                db[table_name].replace_one(filter_q, doc, upsert=True)
            except Exception as e:
                logger.debug(f"MongoDB mirror upsert failed: {e}")

        # Handle deletes
        for instance in list(session.deleted):
            try:
                table_name, filter_q, _ = _instance_to_doc(instance)
                db[table_name].delete_one(filter_q)
            except Exception as e:
                logger.debug(f"MongoDB mirror delete failed: {e}")


def get_mongo_status() -> dict[str, Any]:
    """Returns real-time health and document counts from MongoDB Atlas."""
    client = get_mongo_client()
    if client is None:
        return {"connected": False, "error": "MongoDB Atlas connection not established or disabled"}

    try:
        ping = client.admin.command("ping")
        db = get_mongo_db()
        collections = {}
        if db is not None:
            for name in db.list_collection_names():
                if not name.startswith("system."):
                    collections[name] = db[name].count_documents({})

        return {
            "connected": True,
            "database": config.MONGODB_DB_NAME,
            "ping": ping,
            "collections": collections,
            "total_documents": sum(collections.values()),
        }
    except Exception as e:
        return {"connected": False, "error": str(e)}
