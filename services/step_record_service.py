"""
步骤记录管理服务 - 管理各个步骤的独立MongoDB集合
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any,List
from bson import ObjectId
from pymongo.collection import Collection

from utils.database import mongo_db
from models.step_models import (
    ReportAskQuestions, ReportPlan, ReportSerp,
    ReportSearch, ReportSearchSummary, SerpTask, finalReport
)

logger = logging.getLogger(__name__)


class StepRecordService:
    """步骤记录管理服务"""
    
    def __init__(self):
        # 初始化各个集合
        self.ask_questions_collection: Collection = mongo_db.report_ask_questions
        self.plan_collection: Collection = mongo_db.report_plan
        self.serp_collection: Collection = mongo_db.report_serp
        self.serp_task_collection: Collection = mongo_db.serp_task
        self.search_collection: Collection = mongo_db.report_search
        self.search_summary_collection: Collection = mongo_db.report_search_summary
        self.final_collection: Collection = mongo_db.report_final
        
        # 创建索引
        self._ensure_indexes()
    
    def _ensure_indexes(self):
        """确保必要的索引存在"""
        try:
            collections = [
                self.ask_questions_collection,
                self.plan_collection,
                self.serp_collection,
                self.serp_task_collection,
                self.search_collection,
                self.search_summary_collection
            ]
            
            for collection in collections:
                collection.create_index("report_id")
                collection.create_index("created_at")
                collection.create_index("status")
            
            # 为serp_task集合创建额外的索引
            self.serp_task_collection.create_index("serp_record_id")
            self.serp_task_collection.create_index("split_id")
            
            logger.info("步骤记录集合索引创建完成")
        except Exception as e:
            logger.warning(f"创建步骤记录索引时出现警告: {e}")
    
    def create_ask_questions_record(self, report_id: str, query: str) -> str:
        """创建询问问题记录"""
        return self._create_record(
            self.ask_questions_collection,
            ReportAskQuestions(report_id=report_id, query=query)
        )
    
    def create_plan_record(self, report_id: str, query: str) -> str:
        """创建计划记录"""
        return self._create_record(
            self.plan_collection,
            ReportPlan(report_id=report_id, query=query)
        )

    def upsert_plan_record(self, report_id: str, query: str) -> str:
        """创建或更新计划记录 - 如果存在相同report_id的记录则更新，否则创建新记录"""
        try:
            # 查找是否已存在相同report_id的记录
            existing_record = self.plan_collection.find_one({"report_id": report_id})
            
            if existing_record:
                # 如果存在，则更新现有记录
                update_data = {
                    "query": query,
                    "status": "processing",
                    "updated_at": datetime.now()
                }
                
                result = self.plan_collection.update_one(
                    {"_id": existing_record["_id"]},
                    {"$set": update_data}
                )
                
                if result.modified_count > 0:
                    record_id = str(existing_record["_id"])
                    logger.info(f"更新计划记录成功，集合: {self.plan_collection.name}, ID: {record_id}")
                    return record_id
                else:
                    raise Exception("更新计划记录失败")
            else:
                # 如果不存在，则创建新记录
                return self.create_plan_record(report_id, query)
                
        except Exception as e:
            logger.error(f"创建或更新计划记录失败，集合: {self.plan_collection.name}, 错误: {e}")
            raise

    def upsert_plan_split_record(self, report_id: str,template_id: str, plan_id: str, original_content: str,
                                chapters_count: int, response: Dict[str, Any], only_key: str,
                                chapter_index: int = None, section_title: str = None) -> str:
        """创建或更新计划拆分记录 - 为每个章节创建独立的记录"""
        try:
            # 如果是已有的report_id，先删除该report_id下的所有记录
            if chapter_index == 1:  # 只在处理第一个章节时删除旧记录
                mongo_db["report_plan_split"].delete_many({"report_id": report_id})
                logger.info(f"删除report_id {report_id} 下的所有旧记录")
            
            # 为每个章节创建独立的记录，使用复合键确保唯一性
            split_data = {
                "report_id": report_id,
                "template_id": template_id,
                "plan_id": plan_id,
                "original_content": original_content,
                "response": response,
                "only_key": only_key,
                "chapter_index": chapter_index,
                "section_title": section_title,
                "created_at": datetime.now()
            }
            
            # 插入新记录
            result = mongo_db["report_plan_split"].insert_one(split_data)
            record_id = str(result.inserted_id)
            logger.info(f"创建章节拆分记录成功，集合: report_plan_split, ID: {record_id}, 章节索引: {chapter_index}")
            return record_id
                
        except Exception as e:
            logger.error(f"创建章节拆分记录失败，集合: report_plan_split, 错误: {e}")
            raise

    def store_chapter_content(self, report_id: str, plan_id: str, split_id: str, 
                             chapter_index: int, chapter_content: str, section_title: str, 
                             only_key: str) -> str:
        """存储单个章节内容到report_plan_split_chapters集合"""
        try:
            # 先删除该report_id下的所有章节记录（保持一个report_id下只有一个split记录的逻辑）
            mongo_db["report_plan_split_chapters"].delete_many({"report_id": report_id})
            
            # 创建新的章节记录
            chapter_data = {
                "report_id": report_id,
                "plan_id": plan_id,
                "split_id": split_id,
                "chapter_index": chapter_index,
                "chapter_content": chapter_content,
                "section_title": section_title,
                "only_key": only_key,
                "created_at": datetime.now(),
                "updated_at": datetime.now()
            }
            
            result = mongo_db["report_plan_split_chapters"].insert_one(chapter_data)
            record_id = str(result.inserted_id)
            logger.info(f"存储章节内容成功，集合: report_plan_split_chapters, ID: {record_id}")
            return record_id
                
        except Exception as e:
            logger.error(f"存储章节内容失败，集合: report_plan_split_chapters, 错误: {e}")
            raise

    def create_final_report(self, report_id: str, split_id: str,chapter_index : int,current: str) -> str:
        """创建建议记录"""
        return self._create_record(
            self.final_collection,
            finalReport(report_id=report_id, split_id=split_id,chapter_index=chapter_index, current=current)
        )

    def delete_final_report(self, report_id: str, split_id: str):
        """删除指定report_id和split_id的最终报告记录"""
        try:
            # 验证参数
            if not report_id or not split_id:
                logger.warning("删除最终报告记录失败：report_id或split_id为空")
                return {"deleted_count": 0, "message": "report_id或split_id不能为空"}
            
            # 删除条件：同时匹配report_id和split_id
            delete_filter = {
                "report_id": report_id,
                "split_id": split_id
            }
            
            # 执行删除操作
            result = self.final_collection.delete_many(delete_filter)
            
            # 记录删除结果
            logger.info(f"删除最终报告记录完成，report_id: {report_id}, split_id: {split_id}, 删除了 {result.deleted_count} 条记录")
            
            return {
                "deleted_count": result.deleted_count,
                "report_id": report_id,
                "split_id": split_id,
                "message": f"成功删除{result.deleted_count}条最终报告记录"
            }
            
        except Exception as e:
            error_msg = f"删除最终报告记录失败，report_id: {report_id}, split_id: {split_id}, 错误: {str(e)}"
            logger.error(error_msg)
            raise

    
    def create_serp_record(self, report_id: str,split_id: str, query: str, plan: str = None,
                           current: str = None,tasks: List[Dict[str, Any]] = None, only_key: str = None) -> str:
        """创建SERP记录 - 先删除相同split_id的记录，再创建新记录"""
        try:
            # 先删除相同split_id的所有记录
            self._delete_existing_serp_records(split_id)
            
            # 创建新记录
            return self._create_record(
                self.serp_collection,
                ReportSerp(report_id=report_id,split_id=split_id, query=query, plan=plan, current=current,tasks= tasks, only_key=only_key)
            )
        except Exception as e:
            logger.error(f"创建SERP记录失败: {e}")
            raise
    
    def _delete_existing_serp_records(self, split_id: str):
        """删除相同split_id的所有SERP记录和相关的task记录"""
        try:
            # 查询是否存在相同split_id的SERP记录
            existing_serp_records = list(self.serp_collection.find({"split_id": split_id}))
            
            if existing_serp_records:
                # 收集所有需要删除的serp_record_id
                serp_record_ids = [str(record["_id"]) for record in existing_serp_records]
                
                # 删除SERP记录
                serp_delete_result = self.serp_collection.delete_many({"split_id": split_id})
                if serp_delete_result.deleted_count > 0:
                    logger.info(f"删除了 {serp_delete_result.deleted_count} 条相同split_id的SERP记录，split_id: {split_id}")
                
                # 删除相关的任务记录
                if serp_record_ids:
                    task_delete_result = self.serp_task_collection.delete_many({"serp_record_id": {"$in": serp_record_ids}})
                    if task_delete_result.deleted_count > 0:
                        logger.info(f"删除了 {task_delete_result.deleted_count} 条相关的SERP任务记录，split_id: {split_id}")
            else:
                logger.info(f"未找到相同split_id的SERP记录，split_id: {split_id}")
                
        except Exception as e:
            logger.error(f"删除现有SERP记录失败: {e}")
            raise

    def create_serp_task_records(self, serp_record_id: str, report_id: str, split_id: str, 
                                tasks: List[Dict[str, Any]]) -> List[str]:
        """批量创建SERP任务记录"""
        try:
            task_ids = []
            for index, task in enumerate(tasks):
                serp_task = SerpTask(
                    serp_record_id=serp_record_id,
                    report_id=report_id,
                    split_id=split_id,
                    query=task.get("query", ""),
                    research_goal=task.get("researchGoal", ""),
                    task_index=index
                )
                
                result = self.serp_task_collection.insert_one(serp_task.dict(by_alias=True, exclude={"id"}))
                task_ids.append(str(result.inserted_id))
            
            logger.info(f"成功创建{len(task_ids)}个SERP任务记录")
            return task_ids
        except Exception as e:
            logger.error(f"创建SERP任务记录失败: {e}")
            raise

    def create_search_summary_record(self, report_id: str, query: str,task_id: str, split_id: str,response: Dict[str, Any]) -> str:
        """创建搜索总结记录"""
        return self._create_record(
            self.search_summary_collection,
            ReportSearchSummary(report_id=report_id, query=query,task_id=task_id, split_id=split_id, response=response)
        )
    
    def _create_record(self, collection: Collection, record) -> str:
        """通用创建记录方法"""
        try:
            result = collection.insert_one(record.dict(by_alias=True, exclude={"id"}))
            record_id = str(result.inserted_id)
            logger.info(f"创建步骤记录成功，集合: {collection.name}, ID: {record_id}")
            return record_id
        except Exception as e:
            logger.error(f"创建步骤记录失败，集合: {collection.name}, 错误: {e}")
            raise
    
    def update_ask_questions_record(self, record_id: str, status: str, 
                                  response: Dict[str, Any] = None, 
                                  execution_time: float = None,
                                  error_message: str = None) -> bool:
        """更新询问问题记录"""
        return self._update_record(
            self.ask_questions_collection, record_id, status, 
            response, execution_time, error_message
        )

    def update_ask_questions_message(self, report_id: str, message: str = None) -> bool:
        """更新询问问题记录"""
        try:
            # 验证record_id是否为空
            if not report_id:
                logger.error("无效的记录ID: record_id为空")
                return False

            update_data = {
                "message": message,
                "updated_at": datetime.now()
            }

            # 使用update_many更新所有匹配record_id字段的记录
            result = self.ask_questions_collection.update_many(
                {"report_id": report_id},
                {"$set": update_data}
            )

            # 检查是否有文档被更新
            if result.matched_count > 0:
                if result.modified_count > 0:
                    logger.info(f"更新了{result.modified_count}条询问问题记录，report_id: {report_id}")
                else:
                    logger.info(f"匹配到{result.matched_count}条记录但未发生变化，report_id: {report_id}")
                return True
            else:
                logger.warning(f"未找到对应的询问问题记录，report_id: {report_id}")
                return False

        except Exception as e:
            logger.error(f"更新询问问题记录失败, report_id: {report_id}, 错误: {e}")
            return False
    
    def update_plan_record(self, record_id: str, status: str, 
                         response: Dict[str, Any] = None, 
                         execution_time: float = None,
                         error_message: str = None,
                         additional_fields: Dict[str, Any] = None) -> bool:
        """更新计划记录"""
        return self._update_record(
            self.plan_collection, record_id, status, 
            response, execution_time, error_message,
            additional_fields
        )
    
    def update_serp_record(self, record_id: str, status: str, 
                         response: Dict[str, Any] = None, 
                         execution_time: float = None,
                         error_message: str = None,
                         tasks: List[Dict[str, Any]] = None) -> bool:
        """更新SERP记录"""
        additional_fields = None
        if tasks is not None:
            additional_fields = {"tasks": tasks}
        
        return self._update_record(
            self.serp_collection, record_id, status, 
            response, execution_time, error_message, additional_fields
        )
    
    def update_search_record(self, record_id: str, status: str, 
                           response: Dict[str, Any] = None, 
                           execution_time: float = None,
                           error_message: str = None,
                           results_count: int = None) -> bool:
        """更新搜索记录"""
        return self._update_record(
            self.search_collection, record_id, status, 
            response, execution_time, error_message,
            additional_fields={"results_count": results_count} if results_count is not None else None
        )
    
    def update_search_summary_record(self, record_id: str, status: str, 
                                   response: Dict[str, Any] = None, 
                                   execution_time: float = None,
                                   error_message: str = None) -> bool:
        """更新搜索总结记录"""
        return self._update_record(
            self.search_summary_collection, record_id, status, 
            response, execution_time, error_message
        )
    
    def _update_record(self, collection: Collection, record_id: str, status: str,
                      response: Dict[str, Any] = None, 
                      execution_time: float = None,
                      error_message: str = None,
                      additional_fields: Dict[str, Any] = None) -> bool:
        """通用更新记录方法"""
        try:
            if not ObjectId.is_valid(record_id):
                logger.error(f"无效的记录ID: {record_id}")
                return False
            
            update_data = {
                "status": status,
                "updated_at": datetime.now()
            }
            
            if response is not None:
                update_data["response"] = response
            
            if execution_time is not None:
                update_data["execution_time"] = execution_time
            
            if error_message is not None:
                update_data["error_message"] = error_message
            
            if additional_fields:
                update_data.update(additional_fields)
            
            result = collection.update_one(
                {"_id": ObjectId(record_id)},
                {"$set": update_data}
            )
            
            if result.modified_count > 0:
                logger.info(f"更新步骤记录成功，集合: {collection.name}, ID: {record_id}")
                return True
            else:
                logger.warning(f"步骤记录未更新，集合: {collection.name}, ID: {record_id}")
                return False
                
        except Exception as e:
            logger.error(f"更新步骤记录失败，集合: {collection.name}, ID: {record_id}, 错误: {e}")
            return False
    
    def get_records_by_report_id(self, report_id: str, step_name: str = None):
        """根据报告ID获取步骤记录"""
        try:
            collections_map = {
                "ask_questions": self.ask_questions_collection,
                "plan": self.plan_collection,
                "serp": self.serp_collection,
                "search": self.search_collection,
                "search_summary": self.search_summary_collection
            }
            
            if step_name and step_name in collections_map:
                # 获取特定步骤的记录
                collection = collections_map[step_name]
                records = list(collection.find({"report_id": report_id}).sort("created_at", -1))
                return {step_name: records}
            else:
                # 获取所有步骤的记录
                all_records = {}
                for name, collection in collections_map.items():
                    records = list(collection.find({"report_id": report_id}).sort("created_at", -1))
                    all_records[name] = records
                return all_records
                
        except Exception as e:
            logger.error(f"获取步骤记录失败，报告ID: {report_id}, 错误: {e}")
            return {}

    def get_report_plan(self, plan_id: str) -> Optional[ReportPlan]:
        """
        获取计划详情
        Args:
            plan_id: 计划ID
        Returns:
            ReportPlan: 计划对象
        """
        try:
            if not ObjectId.is_valid(plan_id):
                return None
            doc = self.plan_collection.find_one({"_id": ObjectId(plan_id)})
            if doc:
                return ReportPlan(**doc)
            return None
        except Exception as e:
            logger.error(f"获取计划失败: {e}")
            return None

    def delete_records_by_report_id(self, report_id: str, collections_to_delete: list = None):
        """
        删除指定report_id的相关记录
        Args:
            report_id: 报告ID
            collections_to_delete: 要删除的集合列表，默认为['report_plan', 'report_plan_split', 'report_serp', 'serp_task']
        Returns:
            dict: 删除结果统计
        """
        try:
            if collections_to_delete is None:
                collections_to_delete = ['report_plan', 'report_plan_split', 'report_serp', 'serp_task']
            
            delete_results = {}
            
            for collection_name in collections_to_delete:
                try:
                    if collection_name == 'report_plan':
                        collection = self.plan_collection
                    elif collection_name == 'report_plan_split':
                        collection = mongo_db.report_plan_split
                    elif collection_name == 'report_serp':
                        collection = self.serp_collection
                    elif collection_name == 'serp_task':
                        collection = self.serp_task_collection
                    else:
                        logger.warning(f"未知的集合名称: {collection_name}")
                        continue
                    
                    result = collection.delete_many({"report_id": report_id})
                    delete_results[collection_name] = result.deleted_count
                    logger.info(f"从集合 {collection_name} 中删除了 {result.deleted_count} 条记录，report_id: {report_id}")
                    
                except Exception as e:
                    logger.error(f"删除集合 {collection_name} 中的记录失败: {e}")
                    delete_results[collection_name] = 0
            
            return delete_results
            
        except Exception as e:
            logger.error(f"删除report_id {report_id} 的记录失败: {e}")
            raise


# 创建全局实例
step_record_service = StepRecordService()