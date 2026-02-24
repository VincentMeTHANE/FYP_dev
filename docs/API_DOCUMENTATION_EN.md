# Deep Research Python API Documentation

## Project Overview

**Project Name**: Deep Research Python  
**Version**: 2.0.0  
**Tech Stack**: FastAPI + LangChain + MCP + MongoDB  
**Description**: Deep Research Report Generation System based on LangChain ReAct Agent

---

## Table of Contents

1. [Base APIs](#1-base-apis)
2. [Report Management APIs](#2-report-management-apis)
3. [Ask Questions APIs](#3-ask-questions-apis)
4. [Plan Generation APIs](#4-plan-generation-apis)
5. [SERP Query APIs](#5-serp-query-apis)
6. [Search APIs](#6-search-apis)
7. [Search Summary APIs](#7-search-summary-apis)
8. [Final Report APIs](#8-final-report-apis)
9. [Knowledge Base Management APIs](#9-knowledge-base-management-apis)
10. [Common Response Format](#10-common-response-format)

---

## 1. Base APIs

### 1.1 Root Path

**Endpoint**: `GET /`

Get basic service information

**Response Example**:
```json
{
  "message": "Deep Research Python - LangChain + MCP Version",
  "version": "2.0.0",
  "features": [
    "LangChain ReAct Agent",
    "Automatic Tool Selection",
    "URL Configured MCP Server",
    "Streaming Response Support"
  ]
}
```

### 1.2 Health Check

**Endpoint**: `GET /health`

Check service health status

**Response Example**:
```json
{
  "status": "healthy",
  "service": "deep-research-python",
  "version": "2.0.0",
  "database": "connected",
  "mcp_tools_count": 5
}
```

---

## 2. Report Management APIs

**Route Prefix**: `/report`

### 2.1 Create Report

**Endpoint**: `POST /report/create`

Create a new research report

**Response Example**:
```json
{
  "code": 0,
  "message": "Report created successfully",
  "data": "654f8a9b2c3d4e5f6a7b8c9d"
}
```

### 2.2 Get Report Detail

**Endpoint**: `GET /report/detail/{report_id}`

Get report details by report ID

**Parameters**:
- `report_id` (string): Report ID

**Response Example**:
```json
{
  "code": 0,
  "message": "Operation successful",
  "data": {
    "_id": "654f8a9b2c3d4e5f6a7b8c9d",
    "title": "Deep Research Report Title",
    "status": "processing",
    "message": "User's research topic",
    "progress_percentage": 50,
    "created_at": "2024-01-01T00:00:00Z"
  }
}
```

### 2.3 Get Report List

**Endpoint**: `GET /report/list`

Query report list with pagination

**Parameters** (Query):
- `page` (int, optional): Page number, starting from 1, default 1
- `page_size` (int, optional): Page size, maximum 100, default 20
- `status` (string, optional): Status filter

### 2.4 Get Report History

**Endpoint**: `GET /report/history`

Get current user's report history (sorted by creation time descending)

**Parameters** (Query):
- `page` (int, optional): Page number, default 1
- `page_size` (int, optional): Page size, maximum 50, default 10

### 2.5 Get Report Progress

**Endpoint**: `GET /report/progress/{report_id}`

Get report execution progress

**Response Example**:
```json
{
  "code": 0,
  "message": "Operation successful",
  "data": {
    "report_id": "654f8a9b2c3d4e5f6a7b8c9d",
    "status": "processing",
    "progress_percentage": 60,
    "completed_steps": 3,
    "total_steps": 5,
    "steps": {
      "ask_questions": {"status": "completed", "completed": true},
      "plan": {"status": "completed", "completed": true},
      "serp": {"status": "completed", "completed": true},
      "search": {"status": "completed", "completed": true},
      "search_summary": {"status": "processing", "completed": false}
    }
  }
}
```

### 2.6 Get Step Result

**Endpoint**: `GET /report/step-result/{report_id}/{step_name}`

Get execution result of a specified step

**Parameters**:
- `report_id` (string): Report ID
- `step_name` (string): Step name (ask_questions, plan, serp, search, search_summary)

### 2.7 Lock/Unlock Report

**Endpoint**: `POST /report/lock`

Lock or unlock a report to prevent concurrent editing

**Request Body**:
```json
{
  "report_id": "654f8a9b2c3d4e5f6a7b8c9d",
  "locked": true
}
```

### 2.8 Delete Report

**Endpoint**: `DELETE /report/{report_id}`

Delete a specified report

**Parameters**:
- `report_id` (string): Report ID

---

## 3. Ask Questions APIs

**Route Prefix**: `/ask_questions`

### 3.1 Stream Ask Questions

**Endpoint**: `POST /ask_questions/stream`

Ask questions to the user to enrich the report plan (streaming output)

**Request Body**:
```json
{
  "message": "User's research topic or query content",
  "report_id": "654f8a9b2c3d4e5f6a7b8c9d",
  "template_id": "optional_template_id"
}
```

**Response**: Server-Sent Events (SSE) streaming response

### 3.2 Get Ask Questions Detail

**Endpoint**: `GET /ask_questions/detail/{report_id}`

Get details of the ask questions step

### 3.3 Update Question

**Endpoint**: `PUT /ask_questions/update`

Update user's question or answer

**Request Body**:
```json
{
  "report_id": "654f8a9b2c3d4e5f6a7b8c9d",
  "message": "Updated message content"
}
```

---

## 4. Plan Generation APIs

**Route Prefix**: `/plan`

### 4.1 Stream Generate Plan

**Endpoint**: `POST /plan/stream`

Generate research report outline (streaming output)

**Request Body**:
```json
{
  "message": "User's research topic",
  "report_id": "654f8a9b2c3d4e5f6a7b8c9d"
}
```

**Response**: Server-Sent Events (SSE) streaming response

### 4.2 Generate Plan Using Template

**Endpoint**: `POST /plan/template/synopsis`

Generate outline after selecting a template

**Request Body**:
```json
{
  "message": "User's research topic",
  "report_id": "654f8a9b2c3d4e5f6a7b8c9d",
  "template_id": "template_id_here"
}
```

### 4.3 Split Plan

**Endpoint**: `POST /plan/split/{report_id}`

Split the generated outline by chapters

**Parameters**:
- `report_id` (string): Report ID

**Response Example**:
```json
{
  "code": 0,
  "message": "Operation successful",
  "data": {
    "split_id": "split_id_here",
    "chapters_count": 3,
    "response": [
      {
        "split_id": "chapter_1_split_id",
        "content": "## Chapter 1 Content...",
        "sectionTitle": "Chapter 1 Title"
      },
      {
        "split_id": "chapter_2_split_id",
        "content": "## Chapter 2 Content...",
        "sectionTitle": "Chapter 2 Title"
      }
    ]
  }
}
```

### 4.4 Get Plan Detail

**Endpoint**: `GET /plan/detail/{report_id}`

Get outline details by report ID

### 4.5 Update Plan

**Endpoint**: `PUT /plan/update`

Update outline content

**Request Body**:
```json
{
  "report_id": "654f8a9b2c3d4e5f6a7b8c9d",
  "plan": "Updated outline content"
}
```

---

## 5. SERP Query APIs

**Route Prefix**: `/serp`

### 5.1 Stream Generate SERP Queries

**Endpoint**: `POST /serp/stream`

Generate SERP query list for each chapter (streaming output)

**Request Body**:
```json
{
  "split_id": "chapter_split_id",
  "report_id": "654f8a9b2c3d4e5f6a7b8c9d"
}
```

**Response**: Server-Sent Events (SSE) streaming response

### 5.2 Get SERP Detail

**Endpoint**: `GET /serp/detail/{report_id}`

Get SERP details by report ID

### 5.3 Get SERP List

**Endpoint**: `GET /serp/list/{report_id}`

Get all SERP task list for the report

### 5.4 Get SERP History

**Endpoint**: `GET /serp/history/{report_id}`

Get SERP history for the report

**Parameters**:
- `report_id` (string): Report ID
- `limit` (int, optional): Return limit, default 10

### 5.5 Get Task IDs

**Endpoint**: `GET /serp/get_task_id/{split_id}`

Get task ID list by chapter ID

### 5.6 Delete SERP Task

**Endpoint**: `DELETE /serp/delete/{task_id}`

Delete specified SERP task

---

## 6. Search APIs

**Route Prefix**: `/search`

### 6.1 Execute Search

**Endpoint**: `POST /search/search`

Execute Tavily search + RAG knowledge base retrieval (hybrid search)

**Request Body**:
```json
{
  "task_id": "serp_task_id",
  "max_results": 10,
  "include_images": true,
  "include_domains": ["example.com"],
  "exclude_domains": ["spam.com"],
  "use_rag": true
}
```

**Parameter Description**:
- `task_id` (string, required): SERP task ID
- `max_results` (int, optional): Maximum results, default 10
- `include_images` (bool, optional): Include images, default true
- `include_domains` (list[string], optional): Domains to include
- `exclude_domains` (list[string], optional): Domains to exclude
- `use_rag` (bool, optional): Use knowledge base retrieval, default true

**Response Example**:
```json
{
  "code": 0,
  "message": "Operation successful",
  "data": {
    "task_id": "task_id_here",
    "query": "Search query content",
    "response_time": 2.5,
    "images": [
      {"url": "image_url", "description": "Image description"}
    ],
    "sources": [
      {
        "title": "Result title",
        "url": "https://example.com",
        "content": "Content summary"
      }
    ],
    "knowledge_count": 3,
    "web_count": 10
  }
}
```

### 6.2 Get Search Detail

**Endpoint**: `GET /search/detail/{task_id}`

Get search details by task ID

---

## 7. Search Summary APIs

**Route Prefix**: `/summary`

### 7.1 Search Summary (Completion Mode)

**Endpoint**: `POST /summary/completion`

Summarize search results (non-streaming)

**Request Body**:
```json
{
  "report_id": "654f8a9b2c3d4e5f6a7b8c9d",
  "task_id": "serp_task_id",
  "search_id": "search_id"
}
```

### 7.2 Search Summary (Stream Mode)

**Endpoint**: `POST /summary/stream`

Summarize search results (streaming output)

**Request Body**:
```json
{
  "report_id": "654f8a9b2c3d4e5f6a7b8c9d",
  "task_id": "serp_task_id",
  "search_id": "search_id"
}
```

**Response**: Server-Sent Events (SSE) streaming response

### 7.3 Get Summary Detail

**Endpoint**: `GET /summary/detail/{report_id}`

Get search summary details by report ID

### 7.4 Get Summary History

**Endpoint**: `GET /summary/history/{report_id}`

Get search summary history for the report

---

## 8. Final Report APIs

**Route Prefix**: `/final`

### 8.1 Stream Generate Final Report

**Endpoint**: `POST /final/stream`

Generate final report chapters based on search summaries (streaming output)

**Request Body**:
```json
{
  "report_id": "654f8a9b2c3d4e5f6a7b8c9d",
  "split_id": "chapter_split_id",
  "requirement": "Optional additional requirements"
}
```

**Response**: Server-Sent Events (SSE) streaming response

### 8.2 Generate Report Summary

**Endpoint**: `POST /final/summary/{report_id}`

Generate summary for the entire report (streaming output)

**Parameters**:
- `report_id` (string): Report ID

### 8.3 Download PDF Report

**Endpoint**: `GET /final/download/pdf/{report_id}`

Download report in PDF format

**Response**: PDF file stream

### 8.4 Download Word Report

**Endpoint**: `GET /final/download/word1/{report_id}`

Download report in Word format

**Response**: DOCX file stream

---

## 9. Knowledge Base Management APIs

**Route Prefix**: `/knowledge`

### 9.1 Upload Document

**Endpoint**: `POST /knowledge/upload`

Upload document to knowledge base

**Request Body** (Multipart):
- `file` (file, required): File to upload (PDF, MD, TXT)
- `category` (string, optional): Document category
- `tags` (string, optional): Document tags (comma-separated)
- `description` (string, optional): Document description
- `author` (string, optional): Document author

**Response Example**:
```json
{
  "code": 0,
  "message": "Operation successful",
  "data": {
    "document_id": "doc_id_here",
    "filename": "document.pdf",
    "chunk_count": 15,
    "status": "completed"
  }
}
```

### 9.2 Delete Document

**Endpoint**: `DELETE /knowledge/document/{document_id}`

Delete document from knowledge base

### 9.3 List Documents

**Endpoint**: `GET /knowledge/documents`

List all documents in knowledge base

**Parameters** (Query):
- `status` (string, optional): Document status filter (active, deleted, all)

### 9.4 Get Document Detail

**Endpoint**: `GET /knowledge/document/{document_id}`

Get detailed information of specified document

### 9.5 Search Knowledge Base

**Endpoint**: `POST /knowledge/search`

Search for relevant content in knowledge base

**Request Body**:
```json
{
  "query": "Search query",
  "top_k": 5,
  "score_threshold": 0.5
}
```

**Parameter Description**:
- `query` (string, required): Search query
- `top_k` (int, optional): Number of results to return, default 5
- `score_threshold` (float, optional): Score threshold, default 0.5

### 9.6 Get Knowledge Base Statistics

**Endpoint**: `GET /knowledge/stats`

Get knowledge base statistics

### 9.7 Initialize Knowledge Base

**Endpoint**: `POST /knowledge/init`

Initialize knowledge base service

---

## 10. Common Response Format

### Success Response

All API success responses use the following format:

```json
{
  "code": 0,
  "message": "Operation successful",
  "data": { ... }
}
```

### Error Response

```json
{
  "code": 400,
  "message": "Error message description",
  "data": null
}
```

### Result Class Definition

```python
class Result(BaseModel, Generic[T]):
    code: int          # Status code, 0 for success, non-0 for failure
    message: str       # Return message
    data: Optional[T] # Return data
```

---

## Report Generation Flow

The complete flow for deep research report generation is as follows:

```
1. Create Report (POST /report/create)
       ↓
2. Ask Questions (POST /ask_questions/stream)
       ↓
3. Generate Plan (POST /plan/stream)
       ↓
4. Split Plan (POST /plan/split/{report_id})
       ↓
5. Generate SERP Queries (POST /serp/stream) × Number of Chapters
       ↓
6. Execute Search (POST /search/search) × Number of SERP Tasks
       ↓
7. Search Summary (POST /summary/stream) × Number of Search Tasks
       ↓
8. Generate Final Report (POST /final/stream) × Number of Chapters
       ↓
9. Generate Report Summary (POST /final/summary/{report_id})
       ↓
10. Download Report (GET /final/download/pdf/{report_id})
```

---

## Error Code Reference

| Error Code | Description |
|------------|-------------|
| 0 | Success |
| 400 | Request Parameter Error |
| 404 | Resource Not Found |
| 429 | Too Many Requests |
| 500 | Internal Server Error |

---

## Notes

1. **Streaming Response**: Most generation APIs use Server-Sent Events (SSE) for streaming output. Clients need to properly handle responses of type `text/event-stream`

2. **Distributed Lock**: Search APIs use distributed locks to prevent the same task from being executed repeatedly

3. **Template Support**: Supports using preset templates to generate outlines and reports

4. **Knowledge Base Retrieval**: Search APIs support hybrid search mode, enabling simultaneous web and local knowledge base searches

5. **PDF/Word Export**: Final reports support export in PDF and Word formats

---

*Document Generated: 2024*
*Project Version: 2.0.0*
