"""
RAG Knowledge Base Retrieval Service
Supports vector search, document management, and hybrid search
"""

import logging
import uuid
import hashlib
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import json

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from qdrant_client.http.exceptions import UnexpectedResponse

from config import settings
from utils.database import mongo_db

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeChunk:
    """Knowledge base document chunk"""
    id: str
    content: str
    source: str
    score: float
    metadata: Dict[str, Any]
    document_name: str = ""
    document_type: str = ""


@dataclass
class Document:
    """Knowledge base document"""
    id: str
    name: str
    type: str
    content: str
    chunks: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


class EmbeddingService:
    """Embedding service supporting Dashscope, OpenAI, and local models"""

    def __init__(self):
        self.embedding_model = settings.RAG_EMBEDDING_MODEL
        self.provider = settings.RAG_EMBEDDING_PROVIDER
        self.vector_size = settings.QDRANT_VECTOR_SIZE
        self._client = None

        if self.provider == "dashscope":
            self.api_key = settings.DASHSCOPE_API_KEY
            self.base_url = settings.DASHSCOPE_EMBEDDING_BASE_URL
        elif self.provider == "openai":
            self.api_key = settings.OPENAI_API_KEY
            self.base_url = settings.OPENAI_EMBEDDING_BASE_URL
        else:
            self.api_key = None
            self.base_url = None

    async def _get_client(self):
        """Get HTTP client"""
        if self._client is None:
            import httpx
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                timeout=60.0
            )
        return self._client

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Embed a list of texts into vectors

        Args:
            texts: List of texts

        Returns:
            List of vectors
        """
        try:
            if self.provider == "dashscope":
                return await self._embed_with_dashscope(texts)
            elif self.provider == "openai":
                return await self._embed_with_openai(texts)
            elif self.provider == "local":
                return await self._embed_with_local(texts)
            else:
                raise ValueError(f"Unsupported embedding provider: {self.provider}")

        except Exception as e:
            logger.error(f"Failed to embed texts: {str(e)}")
            raise

    async def _embed_with_dashscope(self, texts: List[str]) -> List[List[float]]:
        """Use Dashscope embedding API"""
        if not texts:
            logger.warning("Empty texts list provided to embed_texts")
            return []

        texts = [t for t in texts if t and t.strip()]
        if not texts:
            logger.warning("All texts are empty after filtering")
            return []

        logger.info(f"Dashscope embedding: {len(texts)} texts, model: {self.embedding_model}")

        client = await self._get_client()

        batch_size = 10
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            logger.info(f"Processing batch {i//batch_size + 1}: {len(batch)} texts")

            response = await client.post(
                "/embeddings",
                json={
                    "model": self.embedding_model,
                    "input": batch
                }
            )

            if response.status_code != 200:
                raise Exception(f"Dashscope Embedding API error: {response.text}")

            result = response.json()
            embeddings = [item["embedding"] for item in result["data"]]
            all_embeddings.extend(embeddings)

        logger.info(f"Dashscope: Successfully embedded {len(texts)} texts")
        return all_embeddings

    async def _embed_with_openai(self, texts: List[str]) -> List[List[float]]:
        """Use OpenAI embedding API"""
        if not texts:
            return []

        client = await self._get_client()

        batch_size = 100
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]

            response = await client.post(
                "/embeddings",
                json={
                    "model": self.embedding_model,
                    "input": batch
                }
            )

            if response.status_code != 200:
                raise Exception(f"OpenAI Embedding API error: {response.text}")

            result = response.json()
            embeddings = [item["embedding"] for item in result["data"]]
            all_embeddings.extend(embeddings)

        logger.info(f"OpenAI: Successfully embedded {len(texts)} texts")
        return all_embeddings

    async def _embed_with_local(self, texts: List[str]) -> List[List[float]]:
        """Use local embedding model"""
        try:
            from sentence_transformers import SentenceTransformer

            if not hasattr(self, "_local_model"):
                self._local_model = SentenceTransformer(self.embedding_model)

            embeddings = self._local_model.encode(texts, convert_to_numpy=True)
            result = [emb.tolist() for emb in embeddings]

            logger.info(f"Local: Successfully embedded {len(texts)} texts")
            return result

        except Exception as e:
            logger.error(f"Local embedding failed: {str(e)}")
            raise

    async def embed_query(self, query: str) -> List[float]:
        """
        Embed a query string

        Args:
            query: Query text

        Returns:
            Query vector
        """
        embeddings = await self.embed_texts([query])
        return embeddings[0]


class DocumentProcessor:
    """Document processing service for PDF and MD files"""

    @staticmethod
    def process_pdf(file_content: bytes, filename: str) -> List[Dict[str, Any]]:
        """
        Process PDF file, extract text and split into chunks

        Args:
            file_content: PDF file content (bytes)
            filename: File name

        Returns:
            List of processed document chunks
        """
        try:
            from pypdf import PdfReader
            from langchain.text_splitter import RecursiveCharacterTextSplitter

            import io
            pdf_file = io.BytesIO(file_content)
            reader = PdfReader(pdf_file)

            full_text = ""
            page_texts = []

            for page_num, page in enumerate(reader.pages):
                text = page.extract_text()
                if text:
                    page_texts.append({
                        "page": page_num + 1,
                        "text": text.strip()
                    })
                    full_text += f"\n\n--- Page {page_num + 1} ---\n\n" + text

            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=settings.RAG_CHUNK_SIZE,
                chunk_overlap=settings.RAG_CHUNK_OVERLAP,
                separators=["\n\n", "\n", "。", "！", "？", " ", ""]
            )

            chunks = text_splitter.split_text(full_text)

            documents = []
            for idx, chunk in enumerate(chunks):
                page_num = 1
                for page_text in page_texts:
                    if page_text["text"] in chunk or chunk in page_text["text"]:
                        page_num = page_text["page"]
                        break

                documents.append({
                    "content": chunk,
                    "metadata": {
                        "source": filename,
                        "type": "pdf",
                        "chunk_index": idx,
                        "total_chunks": len(chunks),
                        "page": page_num
                    }
                })

            logger.info(f"Processed PDF {filename}: {len(chunks)} chunks extracted")
            return documents

        except Exception as e:
            logger.error(f"Failed to process PDF {filename}: {str(e)}")
            raise

    @staticmethod
    def process_markdown(file_content: bytes, filename: str) -> List[Dict[str, Any]]:
        """
        Process Markdown file, extract text and split into chunks

        Args:
            file_content: MD file content (bytes)
            filename: File name

        Returns:
            List of processed document chunks
        """
        try:
            from langchain.text_splitter import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

            text = file_content.decode('utf-8')

            markdown_splitter = MarkdownHeaderTextSplitter(
                headers_to_split_on=[
                    ("#", "H1"),
                    ("##", "H2"),
                    ("###", "H3"),
                    ("####", "H4"),
                ]
            )

            md_header_splits = markdown_splitter.split_text(text)

            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=settings.RAG_CHUNK_SIZE,
                chunk_overlap=settings.RAG_CHUNK_OVERLAP,
                separators=["\n\n", "\n", "。", "！", "？", " ", ""]
            )

            documents = []
            for idx, split in enumerate(md_header_splits):
                content = split.page_content
                metadata = split.metadata

                if len(content) > settings.RAG_CHUNK_SIZE:
                    sub_chunks = text_splitter.split_text(content)
                    for sub_idx, sub_chunk in enumerate(sub_chunks):
                        documents.append({
                            "content": sub_chunk,
                            "metadata": {
                                "source": filename,
                                "type": "md",
                                "chunk_index": f"{idx}_{sub_idx}",
                                "total_chunks": len(sub_chunks),
                                "headers": metadata
                            }
                        })
                else:
                    documents.append({
                        "content": content,
                        "metadata": {
                            "source": filename,
                            "type": "md",
                            "chunk_index": idx,
                            "total_chunks": len(md_header_splits),
                            "headers": metadata
                        }
                    })

            logger.info(f"Processed MD {filename}: {len(documents)} chunks extracted")
            return documents

        except Exception as e:
            logger.error(f"Failed to process MD {filename}: {str(e)}")
            raise

    @staticmethod
    def process_text(file_content: bytes, filename: str) -> List[Dict[str, Any]]:
        """
        Process plain text file

        Args:
            file_content: File content (bytes)
            filename: File name

        Returns:
            List of processed document chunks
        """
        from langchain.text_splitter import RecursiveCharacterTextSplitter

        try:
            text = file_content.decode('utf-8')

            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=settings.RAG_CHUNK_SIZE,
                chunk_overlap=settings.RAG_CHUNK_OVERLAP,
                separators=["\n\n", "\n", "。", "！", "？", " ", ""]
            )

            chunks = text_splitter.split_text(text)

            documents = []
            for idx, chunk in enumerate(chunks):
                documents.append({
                    "content": chunk,
                    "metadata": {
                        "source": filename,
                        "type": "txt",
                        "chunk_index": idx,
                        "total_chunks": len(chunks)
                    }
                })

            logger.info(f"Processed TXT {filename}: {len(documents)} chunks extracted")
            return documents

        except Exception as e:
            logger.error(f"Failed to process TXT {filename}: {str(e)}")
            raise


class RAGService:
    """Main RAG knowledge base retrieval service class"""

    def __init__(self):
        self.embedding_service = EmbeddingService()
        self.document_processor = DocumentProcessor()
        self._qdrant_client = None
        self._initialized = False

    async def initialize(self):
        """Initialize Qdrant connection and collection"""
        if self._initialized:
            return

        try:
            logger.info(f"Connecting to Qdrant at {settings.QDRANT_HOST}:{settings.QDRANT_PORT}")
            self._qdrant_client = QdrantClient(
                url=f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}",
                timeout=30
            )

            collections = self._qdrant_client.get_collections()
            logger.info(f"Connected to Qdrant, available collections: {[c.name for c in collections.collections]}")

            collection_names = [c.name for c in collections.collections]

            if settings.QDRANT_COLLECTION not in collection_names:
                self._qdrant_client.create_collection(
                    collection_name=settings.QDRANT_COLLECTION,
                    vectors_config=VectorParams(
                        size=settings.QDRANT_VECTOR_SIZE,
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"Created Qdrant collection: {settings.QDRANT_COLLECTION}")

            self._initialized = True
            logger.info("RAG Service initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize RAG service: {str(e)}")
            self._qdrant_client = None
            raise

    async def _ensure_initialized(self):
        """Ensure service is initialized"""
        if not self._initialized:
            await self.initialize()

    async def add_documents(
        self,
        file_content: bytes,
        filename: str,
        collection_name: str = None,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Add document to knowledge base

        Args:
            file_content: File content (bytes)
            filename: File name
            collection_name: Collection name (optional)
            metadata: Additional metadata

        Returns:
            Add result
        """
        await self._ensure_initialized()

        collection_name = collection_name or settings.QDRANT_COLLECTION

        file_ext = filename.lower().split('.')[-1] if '.' in filename else ''

        if file_ext == 'pdf':
            documents = self.document_processor.process_pdf(file_content, filename)
        elif file_ext in ['md', 'markdown']:
            documents = self.document_processor.process_markdown(file_content, filename)
        elif file_ext == 'txt':
            documents = self.document_processor.process_text(file_content, filename)
        else:
            raise ValueError(f"Unsupported file type: {file_ext}")

        if metadata:
            for doc in documents:
                doc["metadata"].update(metadata)

        doc_id = hashlib.md5(filename.encode()).hexdigest()[:16]

        texts = [doc["content"] for doc in documents]

        if not texts:
            raise ValueError(f"No text content extracted from file: {filename}")

        texts = [t for t in texts if t and t.strip()]
        if not texts:
            raise ValueError(f"All document chunks are empty after processing: {filename}")

        logger.info(f"Processing document: {filename}, chunks: {len(texts)}")

        embeddings = await self.embedding_service.embed_texts(texts)

        points = []
        for idx, (doc, embedding) in enumerate(zip(documents, embeddings)):
            point_id = str(uuid.uuid4())

            point_metadata = {
                "document_id": doc_id,
                "document_name": filename,
                "document_type": doc["metadata"]["type"],
                "chunk_index": doc["metadata"].get("chunk_index", idx),
                "total_chunks": doc["metadata"].get("total_chunks", len(documents)),
                "source": doc["metadata"].get("source", filename),
                "content": doc["content"],
                **doc["metadata"]
            }

            if metadata:
                point_metadata.update(metadata)

            points.append(
                PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload=point_metadata
                )
            )

        self._qdrant_client.upsert(
            collection_name=collection_name,
            points=points
        )

        await self._save_document_metadata(
            doc_id=doc_id,
            filename=filename,
            file_type=file_ext,
            chunk_count=len(documents),
            metadata=metadata or {}
        )

        logger.info(f"Added document {filename} with {len(documents)} chunks to knowledge base")

        return {
            "document_id": doc_id,
            "filename": filename,
            "chunk_count": len(documents),
            "status": "success"
        }

    async def _save_document_metadata(
        self,
        doc_id: str,
        filename: str,
        file_type: str,
        chunk_count: int,
        metadata: Dict[str, Any]
    ):
        """Save document metadata to MongoDB"""
        try:
            collection = mongo_db["rag_documents"]

            existing_doc = collection.find_one({"_id": doc_id})

            if existing_doc:
                collection.update_one(
                    {"_id": doc_id},
                    {"$set": {
                        "filename": filename,
                        "file_type": file_type,
                        "chunk_count": chunk_count,
                        "metadata": metadata,
                        "status": "active",
                        "updated_at": datetime.now()
                    }}
                )
                logger.info(f"Updated document metadata: {doc_id}")
            else:
                document = {
                    "_id": doc_id,
                    "filename": filename,
                    "file_type": file_type,
                    "chunk_count": chunk_count,
                    "metadata": metadata,
                    "status": "active",
                    "created_at": datetime.now(),
                    "updated_at": datetime.now()
                }
                collection.insert_one(document)
                logger.info(f"Saved document metadata: {doc_id}")

        except Exception as e:
            logger.error(f"Failed to save document metadata: {str(e)}")

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        collection_name: str = None,
        filter_criteria: Dict[str, Any] = None,
        score_threshold: float = 0.5
    ) -> List[KnowledgeChunk]:
        """
        Retrieve relevant documents from knowledge base

        Args:
            query: User query
            top_k: Number of results to return
            collection_name: Collection name
            filter_criteria: Filter conditions
            score_threshold: Score threshold

        Returns:
            List of knowledge base retrieval results
        """
        await self._ensure_initialized()

        if not self._qdrant_client:
            logger.warning("Qdrant client is not initialized")
            return []

        logger.debug(f"Qdrant client type: {type(self._qdrant_client)}")
        logger.debug(f"Qdrant client has search: {hasattr(self._qdrant_client, 'search')}")

        collection_name = collection_name or settings.QDRANT_COLLECTION

        query_embedding = await self.embedding_service.embed_query(query)

        qdrant_filter = None
        if filter_criteria:
            conditions = []
            for key, value in filter_criteria.items():
                conditions.append(
                    FieldCondition(
                        key=key,
                        match=MatchValue(value=value)
                    )
                )
            if conditions:
                from qdrant_client.models import Filter
                qdrant_filter = Filter(must=conditions)

        try:
            search_results = self._qdrant_client.search(
                collection_name=collection_name,
                query_vector=query_embedding,
                limit=top_k,
                query_filter=qdrant_filter,
                score_threshold=score_threshold
            )
        except Exception as e:
            logger.error(f"Qdrant search failed: {str(e)}")
            return []

        chunks = []
        for result in search_results:
            chunk = KnowledgeChunk(
                id=result.id,
                content=result.payload.get("content", ""),
                source="knowledge_base",
                score=result.score,
                metadata=result.payload,
                document_name=result.payload.get("document_name", ""),
                document_type=result.payload.get("document_type", "")
            )
            chunks.append(chunk)

        logger.info(f"Retrieved {len(chunks)} chunks from knowledge base for query: {query[:50]}...")

        return chunks

    async def delete_document(
        self,
        doc_id: str,
        collection_name: str = None
    ) -> bool:
        """
        Delete document from knowledge base

        Args:
            doc_id: Document ID
            collection_name: Collection name

        Returns:
            Whether deletion was successful
        """
        await self._ensure_initialized()

        collection_name = collection_name or settings.QDRANT_COLLECTION

        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue

            self._qdrant_client.delete(
                collection_name=collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="document_id",
                            match=MatchValue(value=doc_id)
                        )
                    ]
                )
            )

            collection = mongo_db["rag_documents"]
            collection.update_one(
                {"_id": doc_id},
                {"$set": {"status": "deleted", "updated_at": datetime.now()}}
            )

            logger.info(f"Deleted document {doc_id} from knowledge base")
            return True

        except Exception as e:
            logger.error(f"Failed to delete document {doc_id}: {str(e)}")
            return False

    async def list_documents(
        self,
        collection_name: str = None,
        status: str = "active"
    ) -> List[Dict[str, Any]]:
        """
        List documents in knowledge base

        Args:
            collection_name: Collection name
            status: Document status filter

        Returns:
            List of documents
        """
        try:
            collection = mongo_db["rag_documents"]

            query = {"status": status} if status else {}

            cursor = collection.find(query).sort("created_at", -1)

            documents = []
            for doc in cursor:
                documents.append({
                    "document_id": str(doc["_id"]),
                    "filename": doc["filename"],
                    "file_type": doc["file_type"],
                    "chunk_count": doc["chunk_count"],
                    "metadata": doc.get("metadata", {}),
                    "status": doc["status"],
                    "created_at": doc["created_at"].isoformat() if doc.get("created_at") else None,
                    "updated_at": doc["updated_at"].isoformat() if doc.get("updated_at") else None
                })

            return documents

        except Exception as e:
            logger.error(f"Failed to list documents: {str(e)}")
            return []

    async def get_document_info(
        self,
        doc_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get detailed document information

        Args:
            doc_id: Document ID

        Returns:
            Document information
        """
        try:
            collection = mongo_db["rag_documents"]
            doc = collection.find_one({"_id": doc_id})

            if not doc:
                return None

            return {
                "document_id": str(doc["_id"]),
                "filename": doc["filename"],
                "file_type": doc["file_type"],
                "chunk_count": doc["chunk_count"],
                "metadata": doc.get("metadata", {}),
                "status": doc["status"],
                "created_at": doc["created_at"].isoformat() if doc.get("created_at") else None,
                "updated_at": doc["updated_at"].isoformat() if doc.get("updated_at") else None
            }

        except Exception as e:
            logger.error(f"Failed to get document info: {str(e)}")
            return None

    async def search_with_hybrid(
        self,
        query: str,
        web_results: List[Dict[str, Any]] = None,
        top_k: int = 5,
        knowledge_weight: float = 0.5
    ) -> Dict[str, Any]:
        """
        Hybrid search combining knowledge base and web search results

        Args:
            query: User query
            web_results: Web search results
            top_k: Number of knowledge base results
            knowledge_weight: Weight for knowledge base results

        Returns:
            Hybrid search results
        """
        knowledge_chunks = await self.retrieve(query, top_k=top_k)

        result = {
            "knowledge": [],
            "web": [],
            "combined_context": ""
        }

        for idx, chunk in enumerate(knowledge_chunks):
            result["knowledge"].append({
                "index": idx,
                "content": chunk.content,
                "score": chunk.score,
                "document_name": chunk.document_name,
                "document_type": chunk.document_type,
                "type": "knowledge"
            })

        if web_results:
            for idx, web_result in enumerate(web_results):
                result["web"].append({
                    "index": idx,
                    "title": web_result.get("title", ""),
                    "url": web_result.get("url", ""),
                    "content": web_result.get("content", ""),
                    "raw_content": web_result.get("raw_content", ""),
                    "score": web_result.get("score", 0),
                    "type": "online"
                })

        context_parts = []

        for kb in result["knowledge"]:
            context_part = f'<content index="{kb["index"]}" type="knowledge" source="knowledge_base" document="{kb["document_name"]}">\n{kb["content"]}\n</content>'
            context_parts.append(context_part)

        for web in result["web"]:
            context_part = f'<content index="{len(result["knowledge"]) + web["index"]}" type="online" source="web" url="{web["url"]}">\n{web.get("raw_content", web.get("content", ""))}\n</content>'
            context_parts.append(context_part)

        result["combined_context"] = "\n".join(context_parts)

        return result


rag_service = RAGService()
