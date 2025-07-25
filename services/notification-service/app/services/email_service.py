"""
Email Service
Business logic for email management and tracking
"""

from typing import Dict, Any, Optional, List
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class EmailService:
    """Email service for tracking and management"""
    
    def __init__(self):
        # In-memory storage for development (replace with database in production)
        self._email_records = {}
    
    async def create_email_record(self, email_data: Dict[str, Any]) -> str:
        """Create a new email record"""
        try:
            email_id = email_data["id"]
            self._email_records[email_id] = email_data
            logger.info(f"📧 Email record created: {email_id}")
            return email_id
        except Exception as e:
            logger.error(f"Failed to create email record: {e}")
            raise
    
    async def update_email_status(self, email_id: str, status: str, update_data: Dict[str, Any]):
        """Update email status and metadata"""
        try:
            if email_id in self._email_records:
                self._email_records[email_id]["status"] = status
                self._email_records[email_id].update(update_data)
                logger.info(f"📧 Email status updated: {email_id} -> {status}")
            else:
                logger.warning(f"Email record not found for update: {email_id}")
        except Exception as e:
            logger.error(f"Failed to update email status: {e}")
            raise
    
    async def get_email_by_id(self, email_id: str) -> Optional[Dict[str, Any]]:
        """Get email record by ID"""
        try:
            return self._email_records.get(email_id)
        except Exception as e:
            logger.error(f"Failed to get email by ID: {e}")
            raise
    
    async def get_email_history(
        self, 
        page: int = 1, 
        per_page: int = 20, 
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Get paginated email history with optional filters"""
        try:
            all_emails = list(self._email_records.values())
            
            # Apply filters
            if filters:
                filtered_emails = []
                for email in all_emails:
                    if self._matches_filters(email, filters):
                        filtered_emails.append(email)
                all_emails = filtered_emails
            
            # Sort by created_at descending
            all_emails.sort(key=lambda x: x.get("created_at", datetime.min), reverse=True)
            
            # Pagination
            total = len(all_emails)
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            emails = all_emails[start_idx:end_idx]
            
            total_pages = (total + per_page - 1) // per_page
            
            return {
                "emails": emails,
                "total": total,
                "page": page,
                "per_page": per_page,
                "pages": total_pages
            }
            
        except Exception as e:
            logger.error(f"Failed to get email history: {e}")
            raise
    
    def _matches_filters(self, email: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        """Check if email matches the given filters"""
        for key, value in filters.items():
            if key == "status" and email.get("status") != value:
                return False
            elif key == "template_name" and email.get("template_name") != value:
                return False
            elif key == "from_date":
                email_date = email.get("created_at")
                if not email_date or email_date < datetime.fromisoformat(value):
                    return False
            elif key == "to_date":
                email_date = email.get("created_at")
                if not email_date or email_date > datetime.fromisoformat(value):
                    return False
        return True

# Global email service instance
email_service = EmailService()

def get_email_service() -> EmailService:
    """Get email service instance"""
    return email_service