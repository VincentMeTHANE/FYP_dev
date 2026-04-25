"""
Report management service using MongoDB
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
    """Report management service"""

    def __init__(self):
        self.collection: Collection = mongo_db.reports
        self._ensure_indexes()

    def _ensure_indexes(self):
        """Ensure required indexes exist"""
        try:
            self.collection.create_index("created_at")
            self.collection.create_index("status")
            self.collection.create_index("message")
            self.collection.create_index([("created_at", DESCENDING)])
            logger.info("MongoDB indexes created successfully")
        except Exception as e:
            logger.warning(f"Index creation warning: {e}")

    def create_report(self, user_id: str = "",tenant_id: str = "1") -> str:
        try:
            report = MongoReport(
                user_id=user_id,
                tenant_id=tenant_id,
                message="",
                title="",
                status="created"
            )

            result = self.collection.insert_one(report.dict(by_alias=True, exclude={"id"}))
            report_id = str(result.inserted_id)

            logger.info(f"Report created successfully, ID: {report_id}")
            return report_id

        except Exception as e:
            logger.error(f"Failed to create report: {e}")
            raise

    def update_report_title(self, report_id: str, title: str):
        """Update report title"""
        self.collection.update_one({"_id": ObjectId(report_id)}, {"$set": {"title": title, "message": title}})

    def get_report(self, report_id: str) -> Optional[MongoReport]:
        """
        Get report details

        Args:
            report_id: Report ID

        Returns:
            MongoReport: Report object
        """
        try:
            if not ObjectId.is_valid(report_id):
                return None

            doc = self.collection.find_one({"_id": ObjectId(report_id)})
            if doc:
                return MongoReport(**doc)
            return None

        except Exception as e:
            logger.error(f"Failed to get report: {e}")
            return None

    def list_reports(self, user_id: str = "", tenant_id: str = "1",page: int = 1, page_size: int = 20,
                    status: Optional[str] = None) -> ReportListResponse:
        """
        Paginated query of report list

        Args:
            page: Page number (starting from 1)
            page_size: Page size
            status: Status filter (optional)

        Returns:
            ReportListResponse: Paginated report list
        """
        try:
            query = {}
            if user_id:
                query["user_id"] = user_id
            if tenant_id:
                query["tenant_id"] = tenant_id
            if status:
                query["status"] = status

            total = self.collection.count_documents(query)

            skip = (page - 1) * page_size
            total_pages = (total + page_size - 1) // page_size

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
            logger.error(f"Failed to query report list: {e}")
            raise

    def update_step_status(self, report_id: str, step_name: str,
                          status: str, result: Optional[Dict[str, Any]] = None,
                          error_message: Optional[str] = None,
                          execution_time: Optional[float] = None) -> bool:
        """
        Update step status

        Args:
            report_id: Report ID
            step_name: Step name (ask_questions, plan, serp, search, search_summary)
            status: Status (pending, processing, completed, failed)
            result: Execution result
            error_message: Error message
            execution_time: Execution time

        Returns:
            bool: Whether update was successful
        """
        try:
            if not ObjectId.is_valid(report_id):
                return False

            now = datetime.now()
            update_data = {
                f"steps.{step_name}.status": status,
                "updated_at": now
            }

            if status == "processing":
                update_data[f"steps.{step_name}.started_at"] = now
            elif status in ["completed", "failed"]:
                update_data[f"steps.{step_name}.completed_at"] = now
                update_data[f"steps.{step_name}.completed"] = (status == "completed")

                if execution_time is not None:
                    update_data[f"steps.{step_name}.execution_time"] = execution_time

            if result is not None:
                update_data[f"steps.{step_name}.result"] = result

            if error_message is not None:
                update_data[f"steps.{step_name}.error_message"] = error_message

            result = self.collection.update_one(
                {"_id": ObjectId(report_id)},
                {"$set": update_data}
            )

            if result.modified_count > 0:
                self._update_overall_progress(report_id)
                logger.info(f"Step status updated: {report_id} - {step_name} - {status}")
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to update step status: {e}")
            return False

    def _update_overall_progress(self, report_id: str):
        """Update overall progress"""
        try:
            report = self.get_report(report_id)
            if not report:
                return

            steps = report.steps
            completed_count = 1
            total_count = 5

            step_statuses = [steps.ask_questions, steps.plan, steps.serp, steps.final_report]

            logger.info(f"Step statuses: {step_statuses}")
            step_names = ["ask_questions", "plan", "serp", "final_report"]
            logger.info(f"Report {report_id} step status check:")
            for i, step in enumerate(step_statuses):
                logger.info(f"  {step_names[i]}: completed={step.completed}, status={step.status}")

            for i, step in enumerate(step_statuses):
                if step.completed:
                    if report.template and step_names[i]=="plan":
                        completed_count += 2
                    else:
                        completed_count += 1
                    logger.info(f"Completed count: {completed_count}")

            progress = (completed_count / total_count) * 100
            logger.info(f"Report {report_id} progress: completed_count={completed_count}, total_count={total_count}, progress={progress:.2f}%")

            overall_status = "created"
            if completed_count == total_count:
                overall_status = "completed"
            elif completed_count > 0:
                overall_status = "processing"

            for step in step_statuses:
                if step.status == "failed":
                    overall_status = "failed"
                    break

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
            logger.error(f"Failed to update overall progress: {e}")

    def start_step(self, report_id: str, step_name: str) -> bool:
        """Start executing a step"""
        return self.update_step_status(report_id, step_name, "processing")

    def complete_step(self, report_id: str, step_name: str,
                     result: Optional[Dict[str, Any]] = None,
                     execution_time: Optional[float] = None) -> bool:
        """Complete a step"""
        return self.update_step_status(
            report_id, step_name, "completed",
            result=result, execution_time=execution_time
        )

    def fail_step(self, report_id: str, step_name: str,
                 error_message: str, execution_time: Optional[float] = None) -> bool:
        """Mark step as failed"""
        return self.update_step_status(
            report_id, step_name, "failed",
            error_message=error_message, execution_time=execution_time
        )

    def get_report_response(self, report_id: str) -> Optional[ReportResponse]:
        """Get report response format"""
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
        """Lock or unlock a report"""
        try:
            if not ObjectId.is_valid(report_id):
                return False

            report = self.get_report(report_id)
            if not report:
                return False

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
                logger.info(f"Report lock status updated: {report_id} - locked: {locked}")
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to update report lock status: {e}")
            return False


report_service = ReportService()
