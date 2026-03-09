# OpenSearch is not used with the PostgreSQL backend.
#
# RAG vector search is performed in Python using cosine similarity
# computed directly in asyncpg (postgres_rag.py). No external search
# service is required.
#
# This file is intentionally empty. If you need full-text search
# capabilities in the future, OpenSearch can be re-added here.
