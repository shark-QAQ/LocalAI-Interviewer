from __future__ import annotations

import logging
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from .config import settings

logger = logging.getLogger(__name__)


class VectorStore:
    def __init__(self) -> None:
        self._client = chromadb.PersistentClient(
            path=str(settings.chroma_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )

    def _collection_name(self, project_id: str, collection_prefix: str = "project_") -> str:
        return f"{collection_prefix}{project_id}"

    def get_or_create_collection(self, project_id: str, collection_prefix: str = "project_") -> Any:
        name = self._collection_name(project_id, collection_prefix)
        return self._client.get_or_create_collection(
            name=name,
            metadata={
                "hnsw:space": "cosine",
                "hnsw:construction_ef": 200,
                "hnsw:M": 32,
            },
        )

    def delete_collection(self, project_id: str, collection_prefix: str = "project_") -> None:
        name = self._collection_name(project_id, collection_prefix)
        try:
            self._client.delete_collection(name)
        except Exception:
            logger.warning("Collection %s not found for deletion", name)

    def add_chunks(
        self,
        project_id: str,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]],
        collection_prefix: str = "project_",
    ) -> None:
        collection = self.get_or_create_collection(project_id, collection_prefix)
        batch_size = 100
        for i in range(0, len(ids), batch_size):
            end = i + batch_size
            collection.add(
                ids=ids[i:end],
                documents=documents[i:end],
                embeddings=embeddings[i:end],
                metadatas=metadatas[i:end],
            )

    def query(
        self,
        source_id: str,
        embedding: list[float],
        n_results: int = 5,
        where: dict[str, Any] | None = None,
        collection_prefix: str = "project_",
    ) -> dict[str, Any]:
        """按集合查询。collection_prefix 决定是项目代码/简历/资料哪个知识集合。"""
        collection = self.get_or_create_collection(source_id, collection_prefix)
        kwargs: dict[str, Any] = {
            "query_embeddings": [embedding],
            "n_results": n_results,
        }
        if where:
            kwargs["where"] = where
        return collection.query(**kwargs)

    def count(self, project_id: str) -> int:
        collection = self.get_or_create_collection(project_id)
        return collection.count()


vector_store = VectorStore()
