"""
Step record management service - Manages independent MongoDB collections for each step
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
    """Step record management service"""

    def __init__(self):
        self.ask_questions_collection: Collection = mongo_db.report_ask_questions
        self.plan_collection: Collection = mongo_db.report_plan
        self.serp_collection: Collection = mongo_db.report_serp
        self.serp_task_collection: Collection = mongo_db.serp_task
        self.search_collection: Collection = mongo_db.report_search
        self.search_summary_collection: Collection = mongo_db.report_search_summary
        self.final_collection: Collection = mongo_db.report_final

        self._ensure_indexes()

    def _ensure_indexes(self):
        """Ensure required indexes exist"""
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

            self.serp_task_collection.create_index("serp_record_id")
            self.serp_task_collection.create_index("split_id")

            logger.info("Step record collection indexes created successfully")
        except Exception as e:
            logger.warning(f"Step record index creation warning: {e}")

    def create_ask_questions_record(self, report_id: str, query: str) -> str:
        """Create ask questions record"""
        return self._create_record(
            self.ask_questions_collection,
            ReportAskQuestions(report_id=report_id, query=query)
        )

    def create_plan_record(self, report_id: str, query: str) -> str:
        """Create plan record"""
        return self._create_record(
            self.plan_collection,
            ReportPlan(report_id=report_id, query=query)
        )

    def upsert_plan_record(self, report_id: str, query: str) -> str:
        """Create or update plan record - updates if exists, otherwise creates new"""
        try:
            existing_record = self.plan_collection.find_one({"report_id": report_id})

            if existing_record:
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
                    logger.info(f"Plan record updated, collection: {self.plan_collection.name}, ID: {record_id}")
                    return record_id
                else:
                    raise Exception("Failed to update plan record")
            else:
                return self.create_plan_record(report_id, query)

        except Exception as e:
            logger.error(f"Failed to create or update plan record, collection: {self.plan_collection.name}, error: {e}")
            raise

    def upsert_plan_split_record(self, report_id: str,template_id: str, plan_id: str, original_content: str,
                                chapters_count: int, response: Dict[str, Any], only_key: str,
                                chapter_index: int = None, section_title: str = None) -> str:
        """Create or update plan split record - creates independent record for each chapter"""
        try:
            if chapter_index == 1:
                mongo_db["report_plan_split"].delete_many({"report_id": report_id})
                logger.info(f"Deleted old records for report_id {report_id}")

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

            result = mongo_db["report_plan_split"].insert_one(split_data)
            record_id = str(result.inserted_id)
            logger.info(f"Chapter split record created, collection: report_plan_split, ID: {record_id}, chapter index: {chapter_index}")
            return record_id

        except Exception as e:
            logger.error(f"Failed to create chapter split record, collection: report_plan_split, error: {e}")
            raise

    def store_chapter_content(self, report_id: str, plan_id: str, split_id: str,
                             chapter_index: int, chapter_content: str, section_title: str,
                             only_key: str) -> str:
        """Store individual chapter content to report_plan_split_chapters collection"""
        try:
            mongo_db["report_plan_split_chapters"].delete_many({"report_id": report_id})

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
            logger.info(f"Chapter content stored, collection: report_plan_split_chapters, ID: {record_id}")
            return record_id

        except Exception as e:
            logger.error(f"Failed to store chapter content, collection: report_plan_split_chapters, error: {e}")
            raise

    def create_final_report(self, report_id: str, split_id: str,chapter_index : int,current: str) -> str:
        """Create final report record"""
        return self._create_record(
            self.final_collection,
            finalReport(report_id=report_id, split_id=split_id,chapter_index=chapter_index, current=current)
        )

    def delete_final_report(self, report_id: str, split_id: str):
        """Delete final report record by report_id and split_id"""
        try:
            if not report_id or not split_id:
                logger.warning("Delete failed: report_id or split_id is empty")
                return {"deleted_count": 0, "message": "report_id and split_id cannot be empty"}

            delete_filter = {
                "report_id": report_id,
                "split_id": split_id
            }

            result = self.final_collection.delete_many(delete_filter)

            logger.info(f"Final report records deleted, report_id: {report_id}, split_id: {split_id}, count: {result.deleted_count}")

            return {
                "deleted_count": result.deleted_count,
                "report_id": report_id,
                "split_id": split_id,
                "message": f"Successfully deleted {result.deleted_count} final report records"
            }

        except Exception as e:
            error_msg = f"Failed to delete final report records, report_id: {report_id}, split_id: {split_id}, error: {str(e)}"
            logger.error(error_msg)
            raise


    def create_serp_record(self, report_id: str,split_id: str, query: str, plan: str = None,
                           current: str = None,tasks: List[Dict[str, Any]] = None, only_key: str = None) -> str:
        """Create SERP record - deletes existing records with same split_id, then creates new"""
        try:
            self._delete_existing_serp_records(split_id)

            return self._create_record(
                self.serp_collection,
                ReportSerp(report_id=report_id,split_id=split_id, query=query, plan=plan, current=current,tasks= tasks, only_key=only_key)
            )
        except Exception as e:
            logger.error(f"Failed to create SERP record: {e}")
            raise

    def _delete_existing_serp_records(self, split_id: str):
        """Delete all SERP records and related task records with same split_id"""
        try:
            existing_serp_records = list(self.serp_collection.find({"split_id": split_id}))

            if existing_serp_records:
                serp_record_ids = [str(record["_id"]) for record in existing_serp_records]

                serp_delete_result = self.serp_collection.delete_many({"split_id": split_id})
                if serp_delete_result.deleted_count > 0:
                    logger.info(f"Deleted {serp_delete_result.deleted_count} SERP records with same split_id, split_id: {split_id}")

                if serp_record_ids:
                    task_delete_result = self.serp_task_collection.delete_many({"serp_record_id": {"$in": serp_record_ids}})
                    if task_delete_result.deleted_count > 0:
                        logger.info(f"Deleted {task_delete_result.deleted_count} related SERP task records, split_id: {split_id}")
            else:
                logger.info(f"No existing SERP records with split_id: {split_id}")

        except Exception as e:
            logger.error(f"Failed to delete existing SERP records: {e}")
            raise

    def create_serp_task_records(self, serp_record_id: str, report_id: str, split_id: str,
                                tasks: List[Dict[str, Any]]) -> List[str]:
        """Batch create SERP task records"""
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

            logger.info(f"Successfully created {len(task_ids)} SERP task records")
            return task_ids
        except Exception as e:
            logger.error(f"Failed to create SERP task records: {e}")
            raise

    def create_search_summary_record(self, report_id: str, query: str,task_id: str, split_id: str,response: Dict[str, Any]) -> str:
        """Create search summary record"""
        return self._create_record(
            self.search_summary_collection,
            ReportSearchSummary(report_id=report_id, query=query,task_id=task_id, split_id=split_id, response=response)
        )

    def _create_record(self, collection: Collection, record) -> str:
        """Generic record creation method"""
        try:
            result = collection.insert_one(record.dict(by_alias=True, exclude={"id"}))
            record_id = str(result.inserted_id)
            logger.info(f"Step record created, collection: {collection.name}, ID: {record_id}")
            return record_id
        except Exception as e:
            logger.error(f"Failed to create step record, collection: {collection.name}, error: {e}")
            raise

    def update_ask_questions_record(self, record_id: str, status: str,
                                  response: Dict[str, Any] = None,
                                  execution_time: float = None,
                                  error_message: str = None) -> bool:
        """Update ask questions record"""
        return self._update_record(
            self.ask_questions_collection, record_id, status,
            response, execution_time, error_message
        )

    def update_ask_questions_message(self, report_id: str, message: str = None) -> bool:
        """Update ask questions record message"""
        try:
            if not report_id:
                logger.error("Invalid record ID: report_id is empty")
                return False

            update_data = {
                "message": message,
                "updated_at": datetime.now()
            }

            result = self.ask_questions_collection.update_many(
                {"report_id": report_id},
                {"$set": update_data}
            )

            if result.matched_count > 0:
                if result.modified_count > 0:
                    logger.info(f"Updated {result.modified_count} ask questions records, report_id: {report_id}")
                else:
                    logger.info(f"Matched {result.matched_count} records but no changes, report_id: {report_id}")
                return True
            else:
                logger.warning(f"No matching ask questions records found, report_id: {report_id}")
                return False

        except Exception as e:
            logger.error(f"Failed to update ask questions record, report_id: {report_id}, error: {e}")
            return False

    def update_plan_record(self, record_id: str, status: str,
                         response: Dict[str, Any] = None,
                         execution_time: float = None,
                         error_message: str = None,
                         additional_fields: Dict[str, Any] = None) -> bool:
        """Update plan record"""
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
        """Update SERP record"""
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
        """Update search record"""
        return self._update_record(
            self.search_collection, record_id, status,
            response, execution_time, error_message,
            additional_fields={"results_count": results_count} if results_count is not None else None
        )

    def update_search_summary_record(self, record_id: str, status: str,
                                   response: Dict[str, Any] = None,
                                   execution_time: float = None,
                                   error_message: str = None) -> bool:
        """Update search summary record"""
        return self._update_record(
            self.search_summary_collection, record_id, status,
            response, execution_time, error_message
        )

    def _update_record(self, collection: Collection, record_id: str, status: str,
                      response: Dict[str, Any] = None,
                      execution_time: float = None,
                      error_message: str = None,
                      additional_fields: Dict[str, Any] = None) -> bool:
        """Generic record update method"""
        try:
            if not ObjectId.is_valid(record_id):
                logger.error(f"Invalid record ID: {record_id}")
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
                logger.info(f"Step record updated, collection: {collection.name}, ID: {record_id}")
                return True
            else:
                logger.warning(f"Step record not updated, collection: {collection.name}, ID: {record_id}")
                return False

        except Exception as e:
            logger.error(f"Failed to update step record, collection: {collection.name}, ID: {record_id}, error: {e}")
            return False

    def get_records_by_report_id(self, report_id: str, step_name: str = None):
        """Get step records by report ID"""
        try:
            collections_map = {
                "ask_questions": self.ask_questions_collection,
                "plan": self.plan_collection,
                "serp": self.serp_collection,
                "search": self.search_collection,
                "search_summary": self.search_summary_collection
            }

            if step_name and step_name in collections_map:
                collection = collections_map[step_name]
                records = list(collection.find({"report_id": report_id}).sort("created_at", -1))
                return {step_name: records}
            else:
                all_records = {}
                for name, collection in collections_map.items():
                    records = list(collection.find({"report_id": report_id}).sort("created_at", -1))
                    all_records[name] = records
                return all_records

        except Exception as e:
            logger.error(f"Failed to get step records, report ID: {report_id}, error: {e}")
            return {}

    def get_report_plan(self, plan_id: str) -> Optional[ReportPlan]:
        """Get plan details"""
        try:
            if not ObjectId.is_valid(plan_id):
                return None
            doc = self.plan_collection.find_one({"_id": ObjectId(plan_id)})
            if doc:
                return ReportPlan(**doc)
            return None
        except Exception as e:
            logger.error(f"Failed to get plan: {e}")
            return None

    def delete_records_by_report_id(self, report_id: str, collections_to_delete: list = None):
        """Delete records for specified report_id"""
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
                        logger.warning(f"Unknown collection name: {collection_name}")
                        continue

                    result = collection.delete_many({"report_id": report_id})
                    delete_results[collection_name] = result.deleted_count
                    logger.info(f"Deleted {result.deleted_count} records from collection {collection_name}, report_id: {report_id}")

                except Exception as e:
                    logger.error(f"Failed to delete records from collection {collection_name}: {e}")
                    delete_results[collection_name] = 0

            return delete_results

        except Exception as e:
            logger.error(f"Failed to delete records for report_id {report_id}: {e}")
            raise


step_record_service = StepRecordService()