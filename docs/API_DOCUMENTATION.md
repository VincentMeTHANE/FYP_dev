# Deep Research Python API 接口文档

## 项目概述

**项目名称**: Deep Research Python  
**版本**: 2.0.0  
**技术栈**: FastAPI + LangChain + MongoDB  
**描述**: 基于 LangChain ReAct 智能体的深度研究报告生成系统

---

## 目录

1. [基础接口](#1-基础接口)
2. [报告管理接口](#2-报告管理接口)
3. [提问环节接口](#3-提问环节接口)
4. [大纲生成接口](#4-大纲生成接口)
5. [SERP查询接口](#5-serp查询接口)
6. [搜索接口](#6-搜索接口)
7. [搜索总结接口](#7-搜索总结接口)
8. [最终报告接口](#8-最终报告接口)
9. [知识库管理接口](#9-知识库管理接口)
10. [通用响应格式](#10-通用响应格式)

---

## 1. 基础接口

### 1.1 根路径

**接口**: `GET /`

获取服务基本信息

**响应示例**:
```json
{
  "message": "Deep Research Python - LangChain + MCP版",
  "version": "2.0.0",
  "features": [
    "LangChain ReAct智能体",
    "自动工具选择",
    "URL配置MCP服务器",
    "流式响应支持"
  ]
}
```

### 1.2 健康检查

**接口**: `GET /health`

检查服务健康状态

**响应示例**:
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

## 2. 报告管理接口

**路由前缀**: `/report`

### 2.1 创建报告

**接口**: `POST /report/create`

创建新的研究报告

**响应示例**:
```json
{
  "code": 0,
  "message": "报告创建成功",
  "data": "654f8a9b2c3d4e5f6a7b8c9d"
}
```

### 2.2 获取报告详情

**接口**: `GET /report/detail/{report_id}`

根据报告ID获取报告详情

**参数**:
- `report_id` (string): 报告ID

**响应示例**:
```json
{
  "code": 0,
  "message": "Operation successful",
  "data": {
    "_id": "654f8a9b2c3d4e5f6a7b8c9d",
    "title": "深度研究报告标题",
    "status": "processing",
    "message": "用户的研究主题",
    "progress_percentage": 50,
    "created_at": "2024-01-01T00:00:00Z"
  }
}
```

### 2.3 获取报告列表

**接口**: `GET /report/list`

分页查询报告列表

**参数** (Query):
- `page` (int, optional): 页码，从1开始，默认1
- `page_size` (int, optional): 每页大小，最大100，默认20
- `status` (string, optional): 状态过滤

### 2.4 获取报告历史

**接口**: `GET /report/history`

获取当前用户的报告历史记录（按创建时间倒序）

**参数** (Query):
- `page` (int, optional): 页码，默认1
- `page_size` (int, optional): 每页大小，最大50，默认10

### 2.5 获取报告进度

**接口**: `GET /report/progress/{report_id}`

获取报告执行进度

**响应示例**:
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

### 2.6 获取步骤结果

**接口**: `GET /report/step-result/{report_id}/{step_name}`

获取指定步骤的执行结果

**参数**:
- `report_id` (string): 报告ID
- `step_name` (string): 步骤名称 (ask_questions, plan, serp, search, search_summary)

### 2.7 锁定/解锁报告

**接口**: `POST /report/lock`

锁定或解锁报告，防止并发编辑

**请求体**:
```json
{
  "report_id": "654f8a9b2c3d4e5f6a7b8c9d",
  "locked": true
}
```

### 2.8 删除报告

**接口**: `DELETE /report/{report_id}`

删除指定报告

**参数**:
- `report_id` (string): 报告ID

---

## 3. 提问环节接口

**路由前缀**: `/ask_questions`

### 3.1 流式提问问题

**接口**: `POST /ask_questions/stream`

向用户提问以丰富报告计划（流式输出）

**请求体**:
```json
{
  "message": "用户的研究主题或查询内容",
  "report_id": "654f8a9b2c3d4e5f6a7b8c9d",
  "template_id": "optional_template_id"
}
```

**响应**: Server-Sent Events (SSE) 流式响应

### 3.2 获取提问详情

**接口**: `GET /ask_questions/detail/{report_id}`

获取提问环节的详情

### 3.3 更新问题

**接口**: `PUT /ask_questions/update`

更新用户的问题或回答

**请求体**:
```json
{
  "report_id": "654f8a9b2c3d4e5f6a7b8c9d",
  "message": "更新后的消息内容"
}
```

---

## 4. 大纲生成接口

**路由前缀**: `/plan`

### 4.1 流式生成大纲

**接口**: `POST /plan/stream`

生成研究报告大纲（流式输出）

**请求体**:
```json
{
  "message": "用户的研究主题",
  "report_id": "654f8a9b2c3d4e5f6a7b8c9d"
}
```

**响应**: Server-Sent Events (SSE) 流式响应

### 4.2 使用模板生成大纲

**接口**: `POST /plan/template/synopsis`

选择模板后生成大纲

**请求体**:
```json
{
  "message": "用户的研究主题",
  "report_id": "654f8a9b2c3d4e5f6a7b8c9d",
  "template_id": "template_id_here"
}
```

### 4.3 拆分大纲

**接口**: `POST /plan/split/{report_id}`

将生成的大纲按章节拆分

**参数**:
- `report_id` (string): 报告ID

**响应示例**:
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
        "content": "## 第一章 内容...",
        "sectionTitle": "第一章 章节标题"
      },
      {
        "split_id": "chapter_2_split_id",
        "content": "## 第二章 内容...",
        "sectionTitle": "第二章 章节标题"
      }
    ]
  }
}
```

### 4.4 获取大纲详情

**接口**: `GET /plan/detail/{report_id}`

根据报告ID获取大纲详情

### 4.5 更新大纲

**接口**: `PUT /plan/update`

更新大纲内容

**请求体**:
```json
{
  "report_id": "654f8a9b2c3d4e5f6a7b8c9d",
  "plan": "更新后的大纲内容"
}
```

---

## 5. SERP查询接口

**路由前缀**: `/serp`

### 5.1 流式生成SERP查询

**接口**: `POST /serp/stream`

为每个章节生成SERP查询列表（流式输出）

**请求体**:
```json
{
  "split_id": "chapter_split_id",
  "report_id": "654f8a9b2c3d4e5f6a7b8c9d"
}
```

**响应**: Server-Sent Events (SSE) 流式响应

### 5.2 获取SERP详情

**接口**: `GET /serp/detail/{report_id}`

根据报告ID获取SERP详情

### 5.3 获取SERP列表

**接口**: `GET /serp/list/{report_id}`

获取报告的所有SERP任务列表

### 5.4 获取SERP历史

**接口**: `GET /serp/history/{report_id}`

获取报告的SERP历史记录

**参数**:
- `report_id` (string): 报告ID
- `limit` (int, optional): 返回数量限制，默认10

### 5.5 获取任务ID

**接口**: `GET /serp/get_task_id/{split_id}`

根据章节ID获取对应的任务ID列表

### 5.6 删除SERP任务

**接口**: `DELETE /serp/delete/{task_id}`

删除指定的SERP任务

---

## 6. 搜索接口

**路由前缀**: `/search`

### 6.1 执行搜索

**接口**: `POST /search/search`

执行Tavily搜索 + RAG知识库检索（混合搜索）

**请求体**:
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

**参数说明**:
- `task_id` (string, required): SERP任务ID
- `max_results` (int, optional): 最大结果数，默认10
- `include_images` (bool, optional): 是否包含图片，默认true
- `include_domains` (list[string], optional): 包含的域名
- `exclude_domains` (list[string], optional): 排除的域名
- `use_rag` (bool, optional): 是否使用知识库检索，默认true

**响应示例**:
```json
{
  "code": 0,
  "message": "Operation successful",
  "data": {
    "task_id": "task_id_here",
    "query": "搜索查询内容",
    "response_time": 2.5,
    "images": [
      {"url": "image_url", "description": "图片描述"}
    ],
    "sources": [
      {
        "title": "结果标题",
        "url": "https://example.com",
        "content": "内容摘要"
      }
    ],
    "knowledge_count": 3,
    "web_count": 10
  }
}
```

### 6.2 获取搜索详情

**接口**: `GET /search/detail/{task_id}`

根据任务ID获取搜索详情

---

## 7. 搜索总结接口

**路由前缀**: `/summary`

### 7.1 搜索总结 (Completion模式)

**接口**: `POST /summary/completion`

对搜索结果进行总结（非流式）

**请求体**:
```json
{
  "report_id": "654f8a9b2c3d4e5f6a7b8c9d",
  "task_id": "serp_task_id",
  "search_id": "search_id"
}
```

### 7.2 搜索总结 (Stream模式)

**接口**: `POST /summary/stream`

对搜索结果进行总结（流式输出）

**请求体**:
```json
{
  "report_id": "654f8a9b2c3d4e5f6a7b8c9d",
  "task_id": "serp_task_id",
  "search_id": "search_id"
}
```

**响应**: Server-Sent Events (SSE) 流式响应

### 7.3 获取总结详情

**接口**: `GET /summary/detail/{report_id}`

根据报告ID获取搜索总结详情

### 7.4 获取总结历史

**接口**: `GET /summary/history/{report_id}`

获取报告的搜索总结历史记录

---

## 8. 最终报告接口

**路由前缀**: `/final`

### 8.1 流式生成最终报告

**接口**: `POST /final/stream`

根据搜索总结生成最终报告章节（流式输出）

**请求体**:
```json
{
  "report_id": "654f8a9b2c3d4e5f6a7b8c9d",
  "split_id": "chapter_split_id",
  "requirement": "可选的额外要求"
}
```

**响应**: Server-Sent Events (SSE) 流式响应

### 8.2 生成报告总结

**接口**: `POST /final/summary/{report_id}`

生成整个报告的总结（流式输出）

**参数**:
- `report_id` (string): 报告ID

### 8.3 下载PDF报告

**接口**: `GET /final/download/pdf/{report_id}`

下载PDF格式的报告

**响应**: PDF文件流

### 8.4 下载Word报告

**接口**: `GET /final/download/word1/{report_id}`

下载Word格式的报告

**响应**: DOCX文件流

---

## 9. 知识库管理接口

**路由前缀**: `/knowledge`

### 9.1 上传文档

**接口**: `POST /knowledge/upload`

上传文档到知识库

**请求体** (Multipart):
- `file` (file, required): 要上传的文件 (PDF, MD, TXT)
- `category` (string, optional): 文档分类
- `tags` (string, optional): 文档标签 (逗号分隔)
- `description` (string, optional): 文档描述
- `author` (string, optional): 文档作者

**响应示例**:
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

### 9.2 删除文档

**接口**: `DELETE /knowledge/document/{document_id}`

从知识库删除文档

### 9.3 列出文档

**接口**: `GET /knowledge/documents`

列出知识库中的所有文档

**参数** (Query):
- `status` (string, optional): 文档状态过滤 (active, deleted, all)

### 9.4 获取文档详情

**接口**: `GET /knowledge/document/{document_id}`

获取指定文档的详细信息

### 9.5 搜索知识库

**接口**: `POST /knowledge/search`

在知识库中搜索相关内容

**请求体**:
```json
{
  "query": "搜索查询",
  "top_k": 5,
  "score_threshold": 0.5
}
```

**参数说明**:
- `query` (string, required): 搜索查询
- `top_k` (int, optional): 返回结果数量，默认5
- `score_threshold` (float, optional): 分数阈值，默认0.5

### 9.6 获取知识库统计

**接口**: `GET /knowledge/stats`

获取知识库的统计信息

### 9.7 初始化知识库

**接口**: `POST /knowledge/init`

初始化知识库服务

---

## 10. 通用响应格式

### 成功响应

所有接口的成功响应统一使用以下格式：

```json
{
  "code": 0,
  "message": "Operation successful",
  "data": { ... }
}
```

### 失败响应

```json
{
  "code": 400,
  "message": "错误信息描述",
  "data": null
}
```

### Result 类定义

```python
class Result(BaseModel, Generic[T]):
    code: int          # 状态码，0表示成功，非0表示失败
    message: str       # 返回消息
    data: Optional[T] # 返回数据
```

---

## 报告生成流程

整个深度研究报告生成的完整流程如下：

```
1. 创建报告 (POST /report/create)
       ↓
2. 提问环节 (POST /ask_questions/stream)
       ↓
3. 生成大纲 (POST /plan/stream)
       ↓
4. 拆分大纲 (POST /plan/split/{report_id})
       ↓
5. 生成SERP查询 (POST /serp/stream) × 章节数
       ↓
6. 执行搜索 (POST /search/search) × SERP任务数
       ↓
7. 搜索总结 (POST /summary/stream) × 搜索任务数
       ↓
8. 生成最终报告 (POST /final/stream) × 章节数
       ↓
9. 生成报告总结 (POST /final/summary/{report_id})
       ↓
10. 下载报告 (GET /final/download/pdf/{report_id})
```

---

## 错误代码参考

| 错误代码 | 说明 |
|---------|------|
| 0 | 成功 |
| 400 | 请求参数错误 |
| 404 | 资源不存在 |
| 429 | 请求过于频繁 |
| 500 | 服务器内部错误 |

---

## 注意事项

1. **流式响应**: 大多数生成类接口使用 Server-Sent Events (SSE) 进行流式输出，客户端需要正确处理 `text/event-stream` 类型的响应

2. **分布式锁**: 搜索接口使用了分布式锁来防止同一任务被重复执行

3. **模板功能**: 支持使用预设模板来生成大纲和报告

4. **知识库检索**: 搜索接口支持混合搜索模式，可同时搜索网络和本地知识库

5. **PDF/Word导出**: 最终报告支持导出为 PDF 和 Word 格式