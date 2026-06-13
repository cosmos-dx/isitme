"""Storage layer: clean ABCs plus local-first default implementations.

Backends are pluggable behind the ABCs in ``base.py``:

* ``EventStore``  — append-only event log. Default: SQLite (SQLAlchemy async).
* ``GraphStore``  — typed/weighted/decaying knowledge graph. Default: SQLite.
* ``VectorStore`` — semantic memory. Default: in-process numpy.
* ``OutboxStore`` — durable queue for the cloud sync worker. Default: SQLite.

Postgres/Neo4j/Kùzu/Qdrant/Chroma are documented swap-ins.
"""
