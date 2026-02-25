"""
知识库管理 API
提供文档上传、删除、查询等管理功能
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
    """文档元数据模型"""
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    description: Optional[str] = None
    author: Optional[str] = None


class DocumentQuery(BaseModel):
    """文档查询模型"""
    document_id: Optional[str] = None
    filename: Optional[str] = None
    status: Optional[str] = "active"


class SearchQuery(BaseModel):
    """知识库检索查询模型"""
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
    上传文档到知识库
    
    支持的文件类型: PDF, MD, TXT
    
    Args:
        file: 要上传的文件
        category: 文档分类
        tags: 文档标签 (逗号分隔)
        description: 文档描述
        author: 文档作者
        
    Returns:
        上传结果
    """
    try:
        # 验证文件类型
        allowed_extensions = ['pdf', 'md', 'markdown', 'txt']
        file_ext = file.filename.lower().split('.')[-1] if '.' in file.filename else ''
        
        if file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件类型: {file_ext}. 支持的类型: {', '.join(allowed_extensions)}"
            )
        
        # 读取文件内容
        content = await file.read()
        
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="文件内容为空")
        
        # 构建元数据
        metadata = {}
        if category:
            metadata["category"] = category
        if tags:
            metadata["tags"] = [t.strip() for t in tags.split(',') if t.strip()]
        if description:
            metadata["description"] = description
        if author:
            metadata["author"] = author
        
        # 添加到知识库
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
        raise HTTPException(status_code=500, detail=f"上传文档失败: {str(e)}")


@router.delete("/document/{document_id}", response_model=Result)
async def delete_document(document_id: str):
    """
    从知识库删除文档
    
    Args:
        document_id: 文档 ID
        
    Returns:
        删除结果
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
            raise HTTPException(status_code=404, detail="文档不存在或删除失败")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete document: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除文档失败: {str(e)}")


@router.get("/documents", response_model=Result)
async def list_documents(status: str = "active"):
    """
    列出知识库中的所有文档
    
    Args:
        status: 文档状态过滤 (active, deleted, all)
        
    Returns:
        文档列表
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
        raise HTTPException(status_code=500, detail=f"获取文档列表失败: {str(e)}")


@router.get("/document/{document_id}", response_model=Result)
async def get_document(document_id: str):
    """
    获取文档详细信息
    
    Args:
        document_id: 文档 ID
        
    Returns:
        文档详情
    """
    try:
        document = await rag_service.get_document_info(doc_id=document_id)
        
        if not document:
            raise HTTPException(status_code=404, detail="文档不存在")
        
        return Result.success(document)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get document: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取文档详情失败: {str(e)}")


@router.post("/search", response_model=Result)
async def search_knowledge_base(request: SearchQuery):
    """
    搜索知识库
    
    Args:
        request: 搜索请求
        
    Returns:
        搜索结果
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
        raise HTTPException(status_code=500, detail=f"搜索知识库失败: {str(e)}")


@router.get("/stats", response_model=Result)
async def get_knowledge_base_stats():
    """
    获取知识库统计信息
    
    Returns:
        统计信息
    """
    try:
        # 获取活跃文档数
        active_docs = await rag_service.list_documents(status="active")
        
        # 获取总文档数
        all_docs = await rag_service.list_documents(status=None)
        
        return Result.success({
            "total_documents": len(all_docs),
            "active_documents": len(active_docs),
            "deleted_documents": len(all_docs) - len(active_docs),
            "collection_name": "knowledge_base"
        })
        
    except Exception as e:
        logger.error(f"Failed to get stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取统计信息失败: {str(e)}")


@router.post("/init", response_model=Result)
async def initialize_knowledge_base():
    """
    初始化知识库服务
    
    Returns:
        初始化结果
    """
    try:
        await rag_service.initialize()
        
        return Result.success({
            "status": "initialized",
            "collection": "knowledge_base"
        })
        
    except Exception as e:
        logger.error(f"Failed to initialize knowledge base: {str(e)}")
        raise HTTPException(status_code=500, detail=f"初始化知识库失败: {str(e)}")
