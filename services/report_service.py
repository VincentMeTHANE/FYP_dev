"""
报告管理服务 - 使用MongoDB存储
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from bson import ObjectId
from pymongo import DESCENDING
from pymongo.collection import Collection

from utils.database import mongo_db
from models.mongo_models import (
    MongoReport, ReportResponse, ReportListResponse
)

logger = logging.getLogger(__name__)


class ReportService:
    """报告管理服务"""
    
    def __init__(self):
        self.collection: Collection = mongo_db.reports
        # 创建索引
        self._ensure_indexes()
    
    def _ensure_indexes(self):
        """确保必要的索引存在"""
        try:
            # 创建常用查询的索引
            self.collection.create_index("created_at")
            self.collection.create_index("status")
            self.collection.create_index("message")
            self.collection.create_index([("created_at", DESCENDING)])
            logger.info("MongoDB索引创建完成")
        except Exception as e:
            logger.warning(f"创建索引时出现警告: {e}")
    
    def create_report(self, user_id: str = "",tenant_id: str = "1") -> str:
       
        try:
            report = MongoReport(
                user_id=user_id,
                tenant_id=tenant_id,
                message="",
                title="",
                status="created"
            )
            
            # 插入文档
            result = self.collection.insert_one(report.dict(by_alias=True, exclude={"id"}))
            report_id = str(result.inserted_id)
            
            logger.info(f"创建报告成功，ID: {report_id}")
            return report_id
            
        except Exception as e:
            logger.error(f"创建报告失败: {e}")
            raise
    
    def update_report_title(self, report_id: str, title: str):
        """
        更新报告标题
        """
        self.collection.update_one({"_id": ObjectId(report_id)}, {"$set": {"title": title, "message": title}})

    def get_report(self, report_id: str) -> Optional[MongoReport]:
        """
        获取报告详情
        
        Args:
            report_id: 报告ID
            
        Returns:
            MongoReport: 报告对象
        """
        try:
            if not ObjectId.is_valid(report_id):
                return None
                
            doc = self.collection.find_one({"_id": ObjectId(report_id)})
            if doc:
                return MongoReport(**doc)
            return None
            
        except Exception as e:
            logger.error(f"获取报告失败: {e}")
            return None
    
    def list_reports(self, user_id: str = "", tenant_id: str = "1",page: int = 1, page_size: int = 20,
                    status: Optional[str] = None) -> ReportListResponse:
        """
        分页查询报告列表
        
        Args:
            page: 页码（从1开始）
            page_size: 每页大小
            status: 状态过滤（可选）
            
        Returns:
            ReportListResponse: 分页报告列表
        """
        try:
            # 构建查询条件
            query = {}
            if user_id:
                query["user_id"] = user_id
            if tenant_id:
                query["tenant_id"] = tenant_id
            if status:
                query["status"] = status
            
            # 计算总数
            total = self.collection.count_documents(query)
            
            # 计算分页
            skip = (page - 1) * page_size
            total_pages = (total + page_size - 1) // page_size
            
            # 查询数据
            cursor = self.collection.find(query)\
                .sort("created_at", DESCENDING)\
                .skip(skip)\
                .limit(page_size)
            
            reports = []
            for doc in cursor:
                report = MongoReport(**doc)
                reports.append(ReportResponse(
                    id=str(report.id),
                    message=report.message,
                    title=report.title,
                    status=report.status,
                    created_at=report.created_at,
                    updated_at=report.updated_at,
                    steps=report.steps,
                    total_steps=report.total_steps,
                    completed_steps=report.completed_steps,
                    progress_percentage=report.progress_percentage,
                    locked=report.locked,
                    isFinalReportCompleted=report.isFinalReportCompleted,
                    template=getattr(report, 'template', ''),
                    is_replace=getattr(report, 'is_replace', False)
                ))
            
            return ReportListResponse(
                total=total,
                page=page,
                page_size=page_size,
                total_pages=total_pages,
                reports=reports
            )
            
        except Exception as e:
            logger.error(f"查询报告列表失败: {e}")
            raise
    
    def update_step_status(self, report_id: str, step_name: str, 
                          status: str, result: Optional[Dict[str, Any]] = None,
                          error_message: Optional[str] = None,
                          execution_time: Optional[float] = None) -> bool:
        """
        更新步骤状态
        
        Args:
            report_id: 报告ID
            step_name: 步骤名称 (ask_questions, plan, serp, search, search_summary)
            status: 状态 (pending, processing, completed, failed)
            result: 执行结果
            error_message: 错误信息
            execution_time: 执行时间
            
        Returns:
            bool: 更新是否成功
        """
        try:
            if not ObjectId.is_valid(report_id):
                return False
            
            now = datetime.now()
            update_data = {
                f"steps.{step_name}.status": status,
                "updated_at": now
            }
            
            # 根据状态更新时间
            if status == "processing":
                update_data[f"steps.{step_name}.started_at"] = now
            elif status in ["completed", "failed"]:
                update_data[f"steps.{step_name}.completed_at"] = now
                update_data[f"steps.{step_name}.completed"] = (status == "completed")
                
                if execution_time is not None:
                    update_data[f"steps.{step_name}.execution_time"] = execution_time
            
            # 更新结果和错误信息
            if result is not None:
                update_data[f"steps.{step_name}.result"] = result
            
            if error_message is not None:
                update_data[f"steps.{step_name}.error_message"] = error_message
            
            # 执行更新
            result = self.collection.update_one(
                {"_id": ObjectId(report_id)},
                {"$set": update_data}
            )
            
            if result.modified_count > 0:
                # 更新整体进度
                self._update_overall_progress(report_id)
                logger.info(f"更新步骤状态成功: {report_id} - {step_name} - {status}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"更新步骤状态失败: {e}")
            return False
    
    def _update_overall_progress(self, report_id: str):
        """更新整体进度"""
        try:
            report = self.get_report(report_id)
            if not report:
                return
            
            # 计算完成的步骤数
            steps = report.steps
            # completed_count = 0
            completed_count = 1
            total_count = 5  # 总共5个步骤
            
            # step_statuses = [steps.ask_questions, steps.plan, steps.serp, steps.search, steps.search_summary, steps.final_report]
            # 总共有5个步骤 search, search_summary属于serp 都是第四部 删除
            step_statuses = [steps.ask_questions, steps.plan, steps.serp,steps.final_report]

            logger.info(f"检查bug记录日志：step_statuses: {step_statuses}")
            # 添加调试日志
            # step_names = ["ask_questions", "plan", "serp", "search", "search_summary", "final_report"]
            step_names = ["ask_questions", "plan", "serp", "final_report"]
            logger.info(f"报告 {report_id} 步骤状态检查:")
            for i, step in enumerate(step_statuses):
                logger.info(f"  {step_names[i]}: completed={step.completed}, status={step.status}")
            
            for i, step in enumerate(step_statuses):
                if step.completed:
                    if report.template and step_names[i]=="plan":
                        # 如果使用模板，且是plan 则将步骤数增加2
                        completed_count += 2
                    else:
                        completed_count += 1
                    logger.info(f"检查bug记录日志：completed_count: {completed_count}")
            
            # 计算进度百分比
            progress = (completed_count / total_count) * 100
            logger.info(f"报告 {report_id} 进度计算: completed_count={completed_count}, total_count={total_count}, progress={progress:.2f}%")
            
            # 确定整体状态
            overall_status = "created"
            if completed_count == total_count:
                overall_status = "completed"
            elif completed_count > 0:
                overall_status = "processing"
            
            # 检查是否有失败的步骤
            for step in step_statuses:
                if step.status == "failed":
                    overall_status = "failed"
                    break
            
            # 更新数据库
            self.collection.update_one(
                {"_id": ObjectId(report_id)},
                {
                    "$set": {
                        "completed_steps": completed_count,
                        "total_steps": total_count,
                        "progress_percentage": progress,
                        "status": overall_status,
                        "updated_at": datetime.now()
                    }
                }
            )
            
        except Exception as e:
            logger.error(f"更新整体进度失败: {e}")
    
    def start_step(self, report_id: str, step_name: str) -> bool:
        """
        开始执行步骤
        
        Args:
            report_id: 报告ID
            step_name: 步骤名称
            
        Returns:
            bool: 是否成功
        """
        return self.update_step_status(report_id, step_name, "processing")
    
    def complete_step(self, report_id: str, step_name: str, 
                     result: Optional[Dict[str, Any]] = None,
                     execution_time: Optional[float] = None) -> bool:
        """
        完成步骤
        
        Args:
            report_id: 报告ID
            step_name: 步骤名称
            result: 执行结果
            execution_time: 执行时间
            
        Returns:
            bool: 是否成功
        """
        return self.update_step_status(
            report_id, step_name, "completed", 
            result=result, execution_time=execution_time
        )
    
    def fail_step(self, report_id: str, step_name: str, 
                 error_message: str, execution_time: Optional[float] = None) -> bool:
        """
        标记步骤失败
        
        Args:
            report_id: 报告ID
            step_name: 步骤名称
            error_message: 错误信息
            execution_time: 执行时间
            
        Returns:
            bool: 是否成功
        """
        return self.update_step_status(
            report_id, step_name, "failed", 
            error_message=error_message, execution_time=execution_time
        )
    
    def get_report_response(self, report_id: str) -> Optional[ReportResponse]:
        """
        获取报告响应格式
        
        Args:
            report_id: 报告ID
            
        Returns:
            ReportResponse: 报告响应对象
        """
        report = self.get_report(report_id)
        if not report:
            return None
        
        return ReportResponse(
            id=str(report.id),
            message=report.message,
            title=report.title,
            status=report.status,
            created_at=report.created_at,
            updated_at=report.updated_at,
            steps=report.steps,
            total_steps=report.total_steps,
            completed_steps=report.completed_steps,
            progress_percentage=report.progress_percentage,
            locked=report.locked,
            isFinalReportCompleted=getattr(report, 'isFinalReportCompleted', False),
            template=getattr(report, 'template', '')
        )
    
    def lock_report(self, report_id: str, locked: bool) -> bool:
        """
        锁定或解锁报告
        
        Args:
            report_id: 报告ID
            locked: 锁定状态
            
        Returns:
            bool: 更新是否成功
        """
        try:
            if not ObjectId.is_valid(report_id):
                return False
            
            # 检查报告是否存在
            report = self.get_report(report_id)
            if not report:
                return False
            
            # 更新锁定状态
            result = self.collection.update_one(
                {"_id": ObjectId(report_id)},
                {
                    "$set": {
                        "locked": locked,
                        "updated_at": datetime.now()
                    }
                }
            )
            
            if result.modified_count > 0:
                logger.info(f"更新报告锁定状态成功: {report_id} - locked: {locked}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"更新报告锁定状态失败: {e}")
            return False


# 创建全局实例
report_service = ReportService()
