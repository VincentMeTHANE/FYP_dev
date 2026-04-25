"""
Knowledge Base Management API
Provides document upload, delete, query and other management functions
"""

import logging
import io
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from fastapi.responses import JSONResponse

from pydantic import BaseModel

from services.rag_service import rag_service
from utils.response_models import Result

logger = logging.getLogger(__name__)

router = APIRouter()


# ==================== Request Models ====================

class DocumentMetadata(BaseModel):
    """Document metadata model"""
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    description: Optional[str] = None
    author: Optional[str] = None


class DocumentQuery(BaseModel):
    """Document query model"""
    document_id: Optional[str] = None
    filename: Optional[str] = None
    status: Optional[str] = "active"


class SearchQuery(BaseModel):
    """Knowledge base search query model"""
    query: str
    top_k: Optional[int] = 5
    score_threshold: Optional[float] = 0.5


# ==================== API Endpoints ====================

@router.post("/upload", response_model=Result)
async def upload_document(
    file: UploadFile = File(...),
    category: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    author: Optional[str] = Form(None)
):
    """
    Upload document to knowledge base
    
    Supported file types: PDF, MD, TXT
    
    Args:
        file: File to upload
        category: Document category
        tags: Document tags (comma-separated)
        description: Document description
        author: Document author
        
    Returns:
        Upload result
    """
    try:
        allowed_extensions = ['pdf', 'md', 'markdown', 'txt']
        file_ext = file.filename.lower().split('.')[-1] if '.' in file.filename else ''
        
        if file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {file_ext}. Supported types: {', '.join(allowed_extensions)}"
            )
        
        content = await file.read()
        
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="File content is empty")
        
        metadata = {}
        if category:
            metadata["category"] = category
        if tags:
            metadata["tags"] = [t.strip() for t in tags.split(',') if t.strip()]
        if description:
            metadata["description"] = description
        if author:
            metadata["author"] = author
        
        result = await rag_service.add_documents(
            file_content=content,
            filename=file.filename,
            metadata=metadata
        )
        
        logger.info(f"Document uploaded successfully: {file.filename}")
        
        return Result.success({
            "document_id": result["document_id"],
            "filename": result["filename"],
            "chunk_count": result["chunk_count"],
            "status": result["status"]
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload document: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to upload document: {str(e)}")


@router.delete("/document/{document_id}", response_model=Result)
async def delete_document(document_id: str):
    """
    Delete document from knowledge base
    
    Args:
        document_id: Document ID
        
    Returns:
        Delete result
    """
    try:
        result = await rag_service.delete_document(doc_id=document_id)
        
        if result:
            logger.info(f"Document deleted successfully: {document_id}")
            return Result.success({
                "document_id": document_id,
                "status": "deleted"
            })
        else:
            raise HTTPException(status_code=404, detail="Document does not exist or deletion failed")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete document: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(e)}")


@router.get("/documents", response_model=Result)
async def list_documents(status: str = "active"):
    """
    List all documents in knowledge base
    
    Args:
        status: Document status filter (active, deleted, all)
        
    Returns:
        Document list
    """
    try:
        status_filter = None if status == "all" else status
        documents = await rag_service.list_documents(status=status_filter)
        
        return Result.success({
            "total": len(documents),
            "documents": documents
        })
        
    except Exception as e:
        logger.error(f"Failed to list documents: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list documents: {str(e)}")


@router.get("/document/{document_id}", response_model=Result)
async def get_document(document_id: str):
    """
    Get detailed document information
    
    Args:
        document_id: Document ID
        
    Returns:
        Document details
    """
    try:
        document = await rag_service.get_document_info(doc_id=document_id)
        
        if not document:
            raise HTTPException(status_code=404, detail="Document does not exist")
        
        return Result.success(document)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get document: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get document: {str(e)}")


@router.post("/search", response_model=Result)
async def search_knowledge_base(request: SearchQuery):
    """
    Search knowledge base
    
    Args:
        request: Search request
        
    Returns:
        Search results
    """
    try:
        chunks = await rag_service.retrieve(
            query=request.query,
            top_k=request.top_k,
            score_threshold=request.score_threshold
        )
        
        results = []
        for chunk in chunks:
            results.append({
                "id": chunk.id,
                "content": chunk.content,
                "score": chunk.score,
                "document_name": chunk.document_name,
                "document_type": chunk.document_type,
                "metadata": chunk.metadata
            })
        
        return Result.success({
            "query": request.query,
            "total": len(results),
            "results": results
        })
        
    except Exception as e:
        logger.error(f"Failed to search knowledge base: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to search knowledge base: {str(e)}")


@router.get("/stats", response_model=Result)
async def get_knowledge_base_stats():
    """
    Get knowledge base statistics
    
    Returns:
        Statistics
    """
    try:
        active_docs = await rag_service.list_documents(status="active")
        all_docs = await rag_service.list_documents(status=None)
        
        return Result.success({
            "total_documents": len(all_docs),
            "active_documents": len(active_docs),
            "deleted_documents": len(all_docs) - len(active_docs),
            "collection_name": "knowledge_base"
        })
        
    except Exception as e:
        logger.error(f"Failed to get stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


@router.post("/init", response_model=Result)
async def initialize_knowledge_base():
    """
    Initialize knowledge base service
    
    Returns:
        Initialization result
    """
    try:
        await rag_service.initialize()
        
        return Result.success({
            "status": "initialized",
            "collection": "knowledge_base"
        })
        
    except Exception as e:
        logger.error(f"Failed to initialize knowledge base: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to initialize knowledge base: {str(e)}")
