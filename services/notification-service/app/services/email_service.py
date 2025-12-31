"""
Email Service
Database-backed email management and tracking with asyncpg
"""

import uuid
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

import asyncpg

from app.utils.config import get_db_config

logger = logging.getLogger(__name__)


class EmailService:
    """Email service with PostgreSQL persistence"""

    def __init__(self):
        self._db_pool: Optional[asyncpg.Pool] = None

    async def get_db_pool(self) -> asyncpg.Pool:
        """Get or create database connection pool"""
        if self._db_pool is None:
            db_config = get_db_config()
            self._db_pool = await asyncpg.create_pool(
                host=db_config.postgres_host,
                port=db_config.postgres_port,
                database=db_config.db_name,
                user=db_config.db_service_user,
                password=db_config.db_service_password,
                min_size=5,
                max_size=db_config.pool_size,
                command_timeout=db_config.pool_timeout
            )
            logger.info(f"Database pool created: {db_config.postgres_host}/{db_config.db_name}")
        return self._db_pool

    async def close(self):
        """Close database pool"""
        if self._db_pool:
            await self._db_pool.close()
            self._db_pool = None
            logger.info("Database pool closed")

    async def create_email(
        self,
        to_emails: List[str],
        subject: str,
        html_content: Optional[str] = None,
        text_content: Optional[str] = None,
        cc_emails: Optional[List[str]] = None,
        bcc_emails: Optional[List[str]] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
        reply_to: Optional[str] = None,
        template_name: Optional[str] = None,
        template_variables: Optional[Dict[str, Any]] = None,
        priority: str = "normal",
        tags: Optional[List[str]] = None,
        headers: Optional[Dict[str, str]] = None,
        status: str = "pending",
        scheduled_at: Optional[datetime] = None,
        celery_task_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create email record in database"""
        pool = await self.get_db_pool()
        email_id = str(uuid.uuid4())

        from_email = from_email or get_db_config().db_service_user  # Fallback handled in task

        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO emails (
                    id, to_emails, cc_emails, bcc_emails, subject,
                    html_content, text_content, from_email, from_name,
                    reply_to, template_name, template_variables,
                    priority, tags, headers, status, scheduled_at,
                    celery_task_id, metadata
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                    $11, $12, $13, $14, $15, $16, $17, $18, $19
                )
                """,
                email_id,
                json.dumps(to_emails),
                json.dumps(cc_emails or []),
                json.dumps(bcc_emails or []),
                subject,
                html_content,
                text_content,
                from_email,
                from_name,
                reply_to,
                template_name,
                json.dumps(template_variables or {}),
                priority,
                json.dumps(tags or []),
                json.dumps(headers or {}),
                status,
                scheduled_at or datetime.utcnow(),
                celery_task_id,
                json.dumps(metadata or {})
            )

            # Record creation event
            await self._record_event(conn, email_id, "created", {})

        logger.info(f"Email record created: {email_id}")
        return email_id

    async def get_email_by_id(self, email_id: str) -> Optional[Dict[str, Any]]:
        """Get email record by ID"""
        pool = await self.get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM emails WHERE id = $1",
                email_id
            )
            if row:
                result = dict(row)
                # Parse JSONB fields
                for field in ['to_emails', 'cc_emails', 'bcc_emails', 'template_variables',
                              'tags', 'headers', 'metadata']:
                    if result.get(field):
                        if isinstance(result[field], str):
                            result[field] = json.loads(result[field])
                return result
            return None

    async def update_email_status(
        self,
        email_id: str,
        status: str,
        update_data: Dict[str, Any]
    ):
        """Update email status and metadata"""
        pool = await self.get_db_pool()
        async with pool.acquire() as conn:
            # Build dynamic update query
            set_clauses = ["status = $2", "updated_at = CURRENT_TIMESTAMP"]
            params = [email_id, status]
            param_idx = 3

            field_mapping = {
                "sent_at": "sent_at",
                "delivered_at": "delivered_at",
                "message_id": "message_id",
                "smtp_response": "smtp_response",
                "error_message": "error_message",
                "attempts": "attempts",
                "last_attempt_at": "last_attempt_at",
                "celery_task_id": "celery_task_id",
            }

            for key, column in field_mapping.items():
                if key in update_data:
                    set_clauses.append(f"{column} = ${param_idx}")
                    params.append(update_data[key])
                    param_idx += 1

            query = f"UPDATE emails SET {', '.join(set_clauses)} WHERE id = $1"
            await conn.execute(query, *params)

            # Record status change event
            await self._record_event(conn, email_id, status, update_data)

        logger.info(f"Email status updated: {email_id} -> {status}")

    async def record_email_event(
        self,
        email_id: str,
        event_type: str,
        event_data: Dict[str, Any],
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ):
        """Record an email event"""
        pool = await self.get_db_pool()
        async with pool.acquire() as conn:
            await self._record_event(conn, email_id, event_type, event_data, ip_address, user_agent)

    async def _record_event(
        self,
        conn: asyncpg.Connection,
        email_id: str,
        event_type: str,
        event_data: Dict[str, Any],
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ):
        """Internal method to record event"""
        # Serialize datetime objects in event_data
        serialized_data = {}
        for k, v in event_data.items():
            if isinstance(v, datetime):
                serialized_data[k] = v.isoformat()
            else:
                serialized_data[k] = v

        await conn.execute(
            """
            INSERT INTO email_events (id, email_id, event_type, event_data, ip_address, user_agent)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            str(uuid.uuid4()),
            email_id,
            event_type,
            json.dumps(serialized_data),
            ip_address,
            user_agent
        )

    async def get_email_history(
        self,
        page: int = 1,
        per_page: int = 20,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Get paginated email history"""
        pool = await self.get_db_pool()
        async with pool.acquire() as conn:
            where_clauses = []
            params = []
            param_idx = 1

            if filters:
                if filters.get("status"):
                    where_clauses.append(f"status = ${param_idx}")
                    params.append(filters["status"])
                    param_idx += 1
                if filters.get("template_name"):
                    where_clauses.append(f"template_name = ${param_idx}")
                    params.append(filters["template_name"])
                    param_idx += 1
                if filters.get("from_date"):
                    where_clauses.append(f"created_at >= ${param_idx}")
                    params.append(filters["from_date"])
                    param_idx += 1
                if filters.get("to_date"):
                    where_clauses.append(f"created_at <= ${param_idx}")
                    params.append(filters["to_date"])
                    param_idx += 1

            where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

            # Get total count
            count_query = f"SELECT COUNT(*) FROM emails {where_sql}"
            total = await conn.fetchval(count_query, *params)

            # Get paginated results
            offset = (page - 1) * per_page
            query = f"""
                SELECT id, to_emails, subject, status, priority, from_email,
                       template_name, created_at, sent_at, attempts
                FROM emails
                {where_sql}
                ORDER BY created_at DESC
                LIMIT ${param_idx} OFFSET ${param_idx + 1}
            """
            params.extend([per_page, offset])

            rows = await conn.fetch(query, *params)

            emails = []
            for row in rows:
                email = dict(row)
                if email.get('to_emails') and isinstance(email['to_emails'], str):
                    email['to_emails'] = json.loads(email['to_emails'])
                emails.append(email)

            return {
                "emails": emails,
                "total": total,
                "page": page,
                "per_page": per_page,
                "pages": (total + per_page - 1) // per_page if total else 0
            }

    # Bulk batch methods
    async def create_bulk_batch(
        self,
        template_name: Optional[str],
        subject: Optional[str],
        total_recipients: int,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create bulk email batch record"""
        pool = await self.get_db_pool()
        batch_id = str(uuid.uuid4())

        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO bulk_email_batches (
                    id, template_name, subject, total_recipients,
                    pending_count, metadata
                ) VALUES ($1, $2, $3, $4, $5, $6)
                """,
                batch_id,
                template_name,
                subject,
                total_recipients,
                total_recipients,
                json.dumps(metadata or {})
            )

        logger.info(f"Bulk batch created: {batch_id}, recipients={total_recipients}")
        return batch_id

    async def update_bulk_batch_status(
        self,
        batch_id: str,
        status: str,
        update_data: Dict[str, Any]
    ):
        """Update bulk batch status"""
        pool = await self.get_db_pool()
        async with pool.acquire() as conn:
            set_clauses = ["status = $2"]
            params = [batch_id, status]
            param_idx = 3

            for key in ["started_at", "completed_at", "celery_task_id",
                        "successful_count", "failed_count", "error_message"]:
                if key in update_data:
                    set_clauses.append(f"{key} = ${param_idx}")
                    params.append(update_data[key])
                    param_idx += 1

            query = f"UPDATE bulk_email_batches SET {', '.join(set_clauses)} WHERE id = $1"
            await conn.execute(query, *params)

        logger.info(f"Bulk batch status updated: {batch_id} -> {status}")

    async def update_bulk_batch_progress(
        self,
        batch_id: str,
        successful: int,
        failed: int
    ):
        """Update bulk batch progress counts"""
        pool = await self.get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE bulk_email_batches
                SET successful_count = $2,
                    failed_count = $3,
                    pending_count = total_recipients - $2 - $3
                WHERE id = $1
                """,
                batch_id, successful, failed
            )

    async def get_bulk_batch(self, batch_id: str) -> Optional[Dict[str, Any]]:
        """Get bulk batch by ID"""
        pool = await self.get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM bulk_email_batches WHERE id = $1",
                batch_id
            )
            if row:
                result = dict(row)
                if result.get('metadata') and isinstance(result['metadata'], str):
                    result['metadata'] = json.loads(result['metadata'])
                return result
            return None


# Global email service instance
_email_service: Optional[EmailService] = None


def get_email_service() -> EmailService:
    """Get email service singleton"""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service
