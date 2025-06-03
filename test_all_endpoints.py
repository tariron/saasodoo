#!/usr/bin/env python3
"""
Comprehensive FastAPI Endpoint Testing Script
Tests all endpoints for User Service, Tenant Service, and Instance Service
"""

import requests
import json
import uuid
import time
from datetime import datetime
from typing import Dict, Any, Optional

# Configuration
BASE_URLS = {
    "user": "http://localhost:8001",
    "tenant": "http://localhost:8002", 
    "instance": "http://localhost:8003"
}

# Global variables for test data
test_data = {
    "customer_id": None,
    "auth_token": None,
    "tenant_id": None,
    "instance_id": None
}

class EndpointTester:
    def __init__(self):
        self.session = requests.Session()
        self.test_results = []
        
    def log_test(self, service: str, endpoint: str, method: str, status_code: int, success: bool, response_data: Any = None, error: str = None):
        """Log test result"""
        result = {
            "timestamp": datetime.now().isoformat(),
            "service": service,
            "endpoint": endpoint,
            "method": method,
            "status_code": status_code,
            "success": success,
            "response_data": response_data,
            "error": error
        }
        self.test_results.append(result)
        
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {service.upper()} {method} {endpoint} - {status_code}")
        if error:
            print(f"   Error: {error}")
    
    def make_request(self, service: str, endpoint: str, method: str = "GET", data: Dict = None, headers: Dict = None, expected_status: int = 200) -> tuple:
        """Make HTTP request and return response"""
        url = f"{BASE_URLS[service]}{endpoint}"
        
        try:
            if method == "GET":
                response = self.session.get(url, headers=headers)
            elif method == "POST":
                response = self.session.post(url, json=data, headers=headers)
            elif method == "PUT":
                response = self.session.put(url, json=data, headers=headers)
            elif method == "DELETE":
                response = self.session.delete(url, headers=headers)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            success = response.status_code == expected_status
            response_data = None
            
            try:
                response_data = response.json()
            except:
                response_data = response.text
            
            self.log_test(service, endpoint, method, response.status_code, success, response_data)
            return response, success
            
        except Exception as e:
            self.log_test(service, endpoint, method, 0, False, error=str(e))
            return None, False

    def test_user_service(self):
        """Test all User Service endpoints"""
        print("\n🧪 Testing User Service Endpoints...")
        
        # Health checks
        self.make_request("user", "/health", "GET", expected_status=200)
        self.make_request("user", "/health/database", "GET", expected_status=200)
        
        # Root endpoint
        self.make_request("user", "/", "GET", expected_status=200)
        
        # Registration
        registration_data = {
            "email": f"test_{uuid.uuid4().hex[:8]}@example.com",
            "password": "TestPassword123!",
            "first_name": "Test",
            "last_name": "User",
            "company_name": "Test Company"
        }
        
        response, success = self.make_request("user", "/auth/register", "POST", registration_data, expected_status=201)
        if success and response:
            response_data = response.json()
            if 'customer' in response_data:
                test_data["customer_id"] = response_data['customer']['id']
        
        # Login
        login_data = {
            "email": registration_data["email"],
            "password": registration_data["password"],
            "remember_me": False
        }
        
        response, success = self.make_request("user", "/auth/login", "POST", login_data, expected_status=200)
        if success and response:
            response_data = response.json()
            if 'tokens' in response_data:
                test_data["auth_token"] = response_data['tokens'].get('access_token')
        
        # Authenticated endpoints (if we have a token)
        if test_data["auth_token"]:
            auth_headers = {"Authorization": f"Bearer {test_data['auth_token']}"}
            
            # Auth endpoints
            self.make_request("user", "/auth/me", "GET", headers=auth_headers, expected_status=200)
            
            # User endpoints
            self.make_request("user", "/users/profile", "GET", headers=auth_headers, expected_status=200)
            self.make_request("user", "/users/preferences", "GET", headers=auth_headers, expected_status=200)
            self.make_request("user", "/users/stats", "GET", headers=auth_headers, expected_status=200)
            self.make_request("user", "/users/instances", "GET", headers=auth_headers, expected_status=200)
            self.make_request("user", "/users/billing", "GET", headers=auth_headers, expected_status=200)
            
            # Update profile
            profile_update = {
                "first_name": "Updated Test",
                "last_name": "Updated User"
            }
            self.make_request("user", "/users/profile", "PUT", profile_update, auth_headers, expected_status=200)
            
            # Update preferences
            preferences_update = {
                "theme": "dark",
                "language": "en",
                "timezone": "UTC",
                "email_notifications": True,
                "sms_notifications": False
            }
            self.make_request("user", "/users/preferences", "PUT", preferences_update, auth_headers, expected_status=200)
        
        # Password reset (public endpoint)
        reset_data = {"email": registration_data["email"]}
        self.make_request("user", "/auth/password-reset", "POST", reset_data, expected_status=200)
        
        # Email verification (would need verification token in real scenario)
        verification_data = {
            "email": registration_data["email"],
            "verification_code": "123456"  # This will fail but tests the endpoint
        }
        self.make_request("user", "/auth/verify-email", "POST", verification_data, expected_status=400)

    def test_tenant_service(self):
        """Test all Tenant Service endpoints"""
        print("\n🧪 Testing Tenant Service Endpoints...")
        
        # Health checks
        self.make_request("tenant", "/health", "GET", expected_status=200)
        self.make_request("tenant", "/health/detailed", "GET", expected_status=200)
        self.make_request("tenant", "/health/database", "GET", expected_status=200)
        
        # Root endpoint
        self.make_request("tenant", "/", "GET", expected_status=200)
        
        # Create tenant (requires customer_id)
        if test_data["customer_id"]:
            tenant_data = {
                "customer_id": test_data["customer_id"],
                "name": "Test Tenant",
                "subdomain": f"test-{uuid.uuid4().hex[:8]}",
                "plan": "starter",
                "max_instances": 3,
                "max_users": 10
            }
            
            response, success = self.make_request("tenant", "/api/v1/tenants/", "POST", tenant_data, expected_status=201)
            if success and response:
                response_data = response.json()
                test_data["tenant_id"] = response_data.get("id")
            
            # List tenants for customer
            params = f"?customer_id={test_data['customer_id']}"
            self.make_request("tenant", f"/api/v1/tenants/{params}", "GET", expected_status=200)
            
            # Get tenant details
            if test_data["tenant_id"]:
                self.make_request("tenant", f"/api/v1/tenants/{test_data['tenant_id']}", "GET", expected_status=200)
                
                # Update tenant
                update_data = {
                    "name": "Updated Test Tenant",
                    "max_instances": 5
                }
                self.make_request("tenant", f"/api/v1/tenants/{test_data['tenant_id']}", "PUT", update_data, expected_status=200)
                
                # Get tenant by subdomain
                self.make_request("tenant", f"/api/v1/tenants/subdomain/{tenant_data['subdomain']}", "GET", expected_status=200)
                
                # Activate tenant
                self.make_request("tenant", f"/api/v1/tenants/{test_data['tenant_id']}/activate", "POST", expected_status=200)
                
                # Suspend tenant
                self.make_request("tenant", f"/api/v1/tenants/{test_data['tenant_id']}/suspend", "POST", expected_status=200)
        else:
            print("⚠️  Skipping tenant tests - no customer_id available")

    def test_instance_service(self):
        """Test all Instance Service endpoints"""
        print("\n🧪 Testing Instance Service Endpoints...")
        
        # Health checks
        self.make_request("instance", "/health", "GET", expected_status=200)
        self.make_request("instance", "/health/database", "GET", expected_status=200)
        
        # Root endpoint
        self.make_request("instance", "/", "GET", expected_status=200)
        
        # Create instance (requires tenant_id)
        if test_data["tenant_id"]:
            instance_data = {
                "tenant_id": test_data["tenant_id"],
                "name": "Test Instance",
                "description": "Test Odoo Instance",
                "odoo_version": "17.0",
                "instance_type": "development",
                "cpu_limit": 1.0,
                "memory_limit": "2G",
                "storage_limit": "10G",
                "admin_email": "admin@example.com",
                "demo_data": True,
                "database_name": f"test_db_{uuid.uuid4().hex[:8]}",
                "custom_addons": ["sale", "purchase"]
            }
            
            response, success = self.make_request("instance", "/api/v1/instances/", "POST", instance_data, expected_status=201)
            if success and response:
                response_data = response.json()
                test_data["instance_id"] = response_data.get("id")
            
            # List instances for tenant
            params = f"?tenant_id={test_data['tenant_id']}"
            self.make_request("instance", f"/api/v1/instances/{params}", "GET", expected_status=200)
            
            # Get instance details
            if test_data["instance_id"]:
                self.make_request("instance", f"/api/v1/instances/{test_data['instance_id']}", "GET", expected_status=200)
                
                # Update instance
                update_data = {
                    "description": "Updated Test Instance",
                    "memory_limit": "4G"
                }
                self.make_request("instance", f"/api/v1/instances/{test_data['instance_id']}", "PUT", update_data, expected_status=200)
                
                # Get instance status
                self.make_request("instance", f"/api/v1/instances/{test_data['instance_id']}/status", "GET", expected_status=200)
                
                # Get instance logs
                self.make_request("instance", f"/api/v1/instances/{test_data['instance_id']}/logs", "GET", expected_status=200)
                
                # Instance actions
                actions = ["start", "stop", "restart"]
                for action in actions:
                    action_data = {"action": action}
                    self.make_request("instance", f"/api/v1/instances/{test_data['instance_id']}/actions", "POST", action_data, expected_status=200)
                    time.sleep(1)  # Small delay between actions
                
                # Backup action with parameters
                backup_data = {
                    "action": "backup",
                    "parameters": {
                        "backup_name": f"test_backup_{int(time.time())}"
                    }
                }
                self.make_request("instance", f"/api/v1/instances/{test_data['instance_id']}/actions", "POST", backup_data, expected_status=200)
        else:
            print("⚠️  Skipping instance tests - no tenant_id available")

    def run_all_tests(self):
        """Run all endpoint tests"""
        print("🚀 Starting comprehensive FastAPI endpoint testing...\n")
        
        # Test services in order (dependencies)
        self.test_user_service()
        self.test_tenant_service()  
        self.test_instance_service()
        
        # Summary
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result["success"])
        failed_tests = total_tests - passed_tests
        
        print(f"\n📊 Test Summary:")
        print(f"   Total: {total_tests}")
        print(f"   Passed: {passed_tests}")
        print(f"   Failed: {failed_tests}")
        print(f"   Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        # Save detailed results
        with open("test_results.json", "w") as f:
            json.dump(self.test_results, f, indent=2)
        print(f"\n📄 Detailed results saved to test_results.json")
        
        return self.test_results

if __name__ == "__main__":
    tester = EndpointTester()
    tester.run_all_tests() 