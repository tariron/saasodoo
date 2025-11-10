"""
User Service
Customer profile management and related operations
"""

from typing import Dict, List, Optional
from datetime import datetime
import logging

# Import shared schemas
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../../..'))
from shared.schemas.user import (
    UserResponseSchema, UserProfileSchema, UserPreferencesSchema, UserStatsSchema
)

from app.utils.database import CustomerDatabase, db_manager

logger = logging.getLogger(__name__)

class UserService:
    """Customer management service"""
    
    @staticmethod
    async def get_customer_by_email(email: str) -> Optional[Dict]:
        """
        Get customer by email
        
        Args:
            email: Customer email
            
        Returns:
            dict: Customer data or None
        """
        return await CustomerDatabase.get_customer_by_email(email)
    
    @staticmethod
    async def get_customer_by_id(customer_id: str) -> Optional[Dict]:
        """
        Get customer by ID
        
        Args:
            customer_id: Customer ID
            
        Returns:
            dict: Customer data or None
        """
        return await CustomerDatabase.get_customer_by_id(customer_id)
    
    @staticmethod
    async def get_customer_profile(customer_id: str) -> Optional[UserProfileSchema]:
        """
        Get detailed customer profile with subscription and instance information
        
        Args:
            customer_id: Customer ID
            
        Returns:
            UserProfileSchema: Complete customer profile
        """
        try:
            # Get basic customer data
            customer = await CustomerDatabase.get_customer_by_id(customer_id)
            if not customer:
                return None
            
            # Get subscription information from billing database
            subscription_info = await UserService._get_customer_subscription_info(customer_id)
            
            # Get instance count
            instance_count = await UserService._get_customer_instance_count(customer_id)
            
            # Construct profile
            profile_data = {
                'id': str(customer['id']),  # Convert UUID to string
                'email': customer['email'],
                'first_name': customer['first_name'],
                'last_name': customer['last_name'],
                'phone': None,  # Extended fields would come from metadata
                'company': None,
                'country': None,
                'timezone': None,
                'language': None,
                'avatar_url': None,
                'created_at': customer['created_at'],
                'instance_count': instance_count,
                'subscription_plan': subscription_info.get('plan_name'),
                'subscription_status': subscription_info.get('status'),
                'billing_info': subscription_info.get('billing_info')
            }
            
            return UserProfileSchema(**profile_data)
            
        except Exception as e:
            logger.error(f"Get customer profile failed: {e}")
            return None
    
    @staticmethod
    async def update_customer_profile(customer_id: str, update_data: Dict) -> Optional[UserResponseSchema]:
        """
        Update customer profile
        
        Args:
            customer_id: Customer ID
            update_data: Data to update
            
        Returns:
            UserResponseSchema: Updated customer data
        """
        try:
            # Update customer in database
            success = await CustomerDatabase.update_customer(customer_id, update_data)
            
            if not success:
                return None
            
            # Get updated customer data
            customer = await CustomerDatabase.get_customer_by_id(customer_id)
            if not customer:
                return None
            
            # Get instance count for response
            instance_count = await UserService._get_customer_instance_count(customer_id)
            
            # Get subscription status
            subscription_info = await UserService._get_customer_subscription_info(customer_id)
            
            response_data = {
                'id': str(customer['id']),  # Convert UUID to string
                'email': customer['email'],
                'first_name': customer['first_name'],
                'last_name': customer['last_name'],
                'role': 'user',  # All customers have user role
                'status': 'active' if customer['is_active'] else 'inactive',
                'phone': None,
                'company': None,
                'country': None,
                'timezone': None,
                'language': None,
                'avatar_url': None,
                'last_login': None,
                'created_at': customer['created_at'],
                'updated_at': customer['updated_at'],
                'instance_count': instance_count,
                'subscription_status': subscription_info.get('status')
            }
            
            return UserResponseSchema(**response_data)
            
        except Exception as e:
            logger.error(f"Update customer profile failed: {e}")
            return None
    
    @staticmethod
    async def get_customer_preferences(customer_id: str) -> Optional[UserPreferencesSchema]:
        """
        Get customer preferences
        
        Args:
            customer_id: Customer ID
            
        Returns:
            UserPreferencesSchema: Customer preferences
        """
        try:
            # For now, return default preferences
            # In production, you would store these in a separate table
            default_preferences = {
                'timezone': 'UTC',
                'language': 'en',
                'email_notifications': True,
                'sms_notifications': False,
                'marketing_emails': False,
                'theme': 'light',
                'date_format': 'DD/MM/YYYY',
                'time_format': '24',
                'currency': 'USD'
            }
            
            return UserPreferencesSchema(**default_preferences)
            
        except Exception as e:
            logger.error(f"Get customer preferences failed: {e}")
            return None
    
    @staticmethod
    async def update_customer_preferences(customer_id: str, preferences_data: Dict) -> UserPreferencesSchema:
        """
        Update customer preferences
        
        Args:
            customer_id: Customer ID
            preferences_data: Preferences to update
            
        Returns:
            UserPreferencesSchema: Updated preferences
        """
        try:
            # For now, just return the provided preferences
            # In production, you would store these in a preferences table
            
            # Get current preferences and update with new data
            current_preferences = await UserService.get_customer_preferences(customer_id)
            if current_preferences:
                current_dict = current_preferences.dict()
                current_dict.update(preferences_data)
                return UserPreferencesSchema(**current_dict)
            else:
                return UserPreferencesSchema(**preferences_data)
            
        except Exception as e:
            logger.error(f"Update customer preferences failed: {e}")
            # Return current preferences on error
            return await UserService.get_customer_preferences(customer_id)
    
    @staticmethod
    async def get_customer_stats(customer_id: str) -> UserStatsSchema:
        """
        Get customer statistics
        
        Args:
            customer_id: Customer ID
            
        Returns:
            UserStatsSchema: Customer statistics
        """
        try:
            # Get customer data
            customer = await CustomerDatabase.get_customer_by_id(customer_id)
            
            # Get instance statistics
            instance_stats = await UserService._get_customer_instance_stats(customer_id)
            
            # Calculate account age
            account_age_days = 0
            if customer and customer['created_at']:
                account_age = datetime.utcnow() - customer['created_at']
                account_age_days = account_age.days
            
            # Get subscription info
            subscription_info = await UserService._get_customer_subscription_info(customer_id)
            
            stats_data = {
                'total_instances': instance_stats['total'],
                'active_instances': instance_stats['active'],
                'total_storage_used': instance_stats['storage_gb'],
                'total_bandwidth_used': instance_stats['bandwidth_gb'],
                'last_login': None,  # Would come from session tracking
                'account_age_days': account_age_days,
                'subscription_days_remaining': subscription_info.get('days_remaining')
            }
            
            return UserStatsSchema(**stats_data)
            
        except Exception as e:
            logger.error(f"Get customer stats failed: {e}")
            # Return default stats on error
            return UserStatsSchema()
    
    @staticmethod
    async def delete_customer_account(customer_id: str) -> Dict:
        """
        Delete customer account permanently
        
        Args:
            customer_id: Customer ID
            
        Returns:
            dict: Deletion result
        """
        try:
            # In production, this would:
            # 1. Delete all customer instances
            # 2. Cancel subscriptions
            # 3. Delete all related data
            # 4. Delete customer record

            # Permanently delete the customer record
            success = await CustomerDatabase.delete_customer(customer_id)

            if success:
                logger.info(f"Customer account permanently deleted: {customer_id}")
                return {
                    'success': True,
                    'message': 'Account deleted successfully'
                }
            else:
                return {
                    'success': False,
                    'error': 'Failed to delete account'
                }
            
        except Exception as e:
            logger.error(f"Delete customer account failed: {e}")
            return {
                'success': False,
                'error': 'Account deletion failed'
            }
    
    @staticmethod
    async def deactivate_customer_account(customer_id: str) -> Dict:
        """
        Deactivate customer account temporarily
        
        Args:
            customer_id: Customer ID
            
        Returns:
            dict: Deactivation result
        """
        try:
            success = await CustomerDatabase.update_customer(
                customer_id,
                {'is_active': False}
            )
            
            if success:
                logger.info(f"Customer account deactivated: {customer_id}")
                return {
                    'success': True,
                    'message': 'Account deactivated successfully'
                }
            else:
                return {
                    'success': False,
                    'error': 'Failed to deactivate account'
                }
            
        except Exception as e:
            logger.error(f"Deactivate customer account failed: {e}")
            return {
                'success': False,
                'error': 'Account deactivation failed'
            }
    
    @staticmethod
    async def get_customer_instances(customer_id: str) -> List[Dict]:
        """
        Get customer's Odoo instances
        
        Args:
            customer_id: Customer ID
            
        Returns:
            list: Customer instances
        """
        try:
            # Query tenant database for customer instances
            query = """
            SELECT id, subdomain, domain, odoo_version, status, 
                   database_name, created_at, updated_at
            FROM tenants 
            WHERE user_id = $1
            ORDER BY created_at DESC
            """
            
            instances = await db_manager.execute_query(query, customer_id)
            
            return [dict(instance) for instance in instances]
            
        except Exception as e:
            logger.error(f"Get customer instances failed: {e}")
            return []
    
    @staticmethod
    async def get_customer_billing(customer_id: str) -> Dict:
        """
        Get customer billing information
        
        Args:
            customer_id: Customer ID
            
        Returns:
            dict: Billing information
        """
        try:
            subscription_info = await UserService._get_customer_subscription_info(customer_id)
            
            return {
                'subscription': subscription_info,
                'payment_history': [],  # Would come from billing service
                'next_billing_date': subscription_info.get('current_period_end'),
                'amount_due': subscription_info.get('amount', 0.0)
            }
            
        except Exception as e:
            logger.error(f"Get customer billing failed: {e}")
            return {}
    
    @staticmethod
    async def _get_customer_subscription_info(customer_id: str) -> Dict:
        """Get customer subscription information from billing database"""
        try:
            # TODO: Replace with billing-service API call when implemented
            # For now, return default subscription data to prevent crashes
            return {
                'plan_name': 'Basic',
                'status': 'active',
                'current_period_end': None,
                'amount': 29.99,
                'currency': 'USD',
                'days_remaining': 30,
                'billing_info': {}
            }
            
        except Exception as e:
            logger.error(f"Get subscription info failed: {e}")
            return {
                'plan_name': 'Basic',
                'status': 'active',
                'billing_info': {}
            }
    
    @staticmethod
    async def _get_customer_instance_count(customer_id: str) -> int:
        """Get customer's instance count"""
        try:
            # TODO: Replace with tenant-service API call when implemented  
            # For now, return 0 to prevent crashes until tenant-service is built
            logger.info(f"Returning default instance count (0) for customer: {customer_id}")
            return 0
            
        except Exception as e:
            logger.error(f"Get instance count failed: {e}")
            return 0
    
    @staticmethod
    async def _get_customer_instance_stats(customer_id: str) -> Dict:
        """Get customer instance statistics"""
        try:
            # In production, this would query tenant database and calculate stats
            return {
                'total': await UserService._get_customer_instance_count(customer_id),
                'active': 0,  # Would count active instances
                'storage_gb': 0.0,  # Would calculate total storage
                'bandwidth_gb': 0.0  # Would calculate bandwidth usage
            }
            
        except Exception as e:
            logger.error(f"Get instance stats failed: {e}")
            return {'total': 0, 'active': 0, 'storage_gb': 0.0, 'bandwidth_gb': 0.0} 