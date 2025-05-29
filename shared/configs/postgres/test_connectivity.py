#!/usr/bin/env python3
"""
Database Connectivity Test Script for Odoo SaaS Kit

Tests PostgreSQL and Redis connectivity, verifies database setup,
and validates that all required databases and extensions are available.
"""

import os
import sys
import time
import psycopg2
import redis
from typing import List, Dict, Any

def test_postgres_connection() -> bool:
    """Test PostgreSQL connection and database setup"""
    print("🔍 Testing PostgreSQL connection...")
    
    # Database connection parameters
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    database = os.getenv("POSTGRES_DB", "saas_odoo")
    username = os.getenv("POSTGRES_USER", "odoo_user")
    password = os.getenv("POSTGRES_PASSWORD", "secure_password_change_me")
    

    
    try:
        # Test main database connection
        conn = psycopg2.connect(
            host=host,
            port=port,
            database=database,
            user=username,
            password=password
        )
        
        cursor = conn.cursor()
        
        # Test basic connectivity
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        print(f"✅ PostgreSQL connected: {version}")
        
        # Check if multiple databases exist
        expected_databases = ["auth", "billing", "tenant", "communication", "analytics"]
        cursor.execute("""
            SELECT datname FROM pg_database 
            WHERE datname IN %s
        """, (tuple(expected_databases),))
        
        existing_databases = [row[0] for row in cursor.fetchall()]
        
        print(f"📊 Found databases: {existing_databases}")
        
        for db_name in expected_databases:
            if db_name in existing_databases:
                print(f"✅ Database '{db_name}' exists")
            else:
                print(f"❌ Database '{db_name}' missing")
                return False
        
        # Test extensions in main database
        cursor.execute("""
            SELECT extname FROM pg_extension 
            WHERE extname IN ('uuid-ossp', 'pgcrypto', 'pg_trgm')
        """)
        
        extensions = [row[0] for row in cursor.fetchall()]
        expected_extensions = ['uuid-ossp', 'pgcrypto', 'pg_trgm']
        
        for ext in expected_extensions:
            if ext in extensions:
                print(f"✅ Extension '{ext}' installed")
            else:
                print(f"❌ Extension '{ext}' missing")
        
        cursor.close()
        conn.close()
        
        return True
        
    except Exception as e:
        print(f"❌ PostgreSQL connection failed: {e}")
        return False

def test_individual_databases() -> Dict[str, bool]:
    """Test connection to each individual database"""
    print("\n🔍 Testing individual database connections...")
    
    databases = ["auth", "billing", "tenant", "communication", "analytics"]
    results = {}
    
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    username = os.getenv("POSTGRES_USER", "odoo_user")
    password = os.getenv("POSTGRES_PASSWORD", "secure_password_change_me")
    
    for db_name in databases:
        try:
            conn = psycopg2.connect(
                host=host,
                port=port,
                database=db_name,
                user=username,
                password=password
            )
            
            cursor = conn.cursor()
            
            # Test basic query
            cursor.execute("SELECT 1;")
            result = cursor.fetchone()[0]
            
            # Check if UUID extension is available
            cursor.execute("SELECT uuid_generate_v4();")
            uuid_result = cursor.fetchone()[0]
            
            cursor.close()
            conn.close()
            
            print(f"✅ Database '{db_name}' - Connection OK, UUID working")
            results[db_name] = True
            
        except Exception as e:
            print(f"❌ Database '{db_name}' - Connection failed: {e}")
            results[db_name] = False
    
    return results

def test_redis_connection() -> bool:
    """Test Redis connection"""
    print("\n🔍 Testing Redis connection...")
    
    host = os.getenv("REDIS_HOST", "localhost")
    port = int(os.getenv("REDIS_PORT", "6379"))
    password = os.getenv("REDIS_PASSWORD", None)
    
    try:
        # Create Redis connection
        r = redis.Redis(
            host=host,
            port=port,
            password=password,
            decode_responses=True
        )
        
        # Test connectivity
        pong = r.ping()
        if pong:
            print("✅ Redis connected successfully")
            
            # Test basic operations
            r.set("test_key", "test_value", ex=60)
            value = r.get("test_key")
            
            if value == "test_value":
                print("✅ Redis read/write operations working")
                r.delete("test_key")
                return True
            else:
                print("❌ Redis read/write operations failed")
                return False
        else:
            print("❌ Redis ping failed")
            return False
            
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        return False

def test_database_schemas() -> bool:
    """Test if basic schemas are initialized"""
    print("\n🔍 Testing database schemas...")
    
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    username = os.getenv("POSTGRES_USER", "odoo_user")
    password = os.getenv("POSTGRES_PASSWORD", "secure_password_change_me")
    
    schema_tests = {
        "auth": ["users", "user_sessions", "password_resets"],
        "billing": ["subscriptions", "payments"],
        "tenant": ["tenants", "tenant_configs"],
        "communication": ["email_templates", "email_queue"],
        "analytics": ["user_activities", "system_metrics"]
    }
    
    all_passed = True
    
    for db_name, expected_tables in schema_tests.items():
        try:
            conn = psycopg2.connect(
                host=host,
                port=port,
                database=db_name,
                user=username,
                password=password
            )
            
            cursor = conn.cursor()
            
            # Check if tables exist
            cursor.execute("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = ANY(%s)
            """, (expected_tables,))
            
            existing_tables = [row[0] for row in cursor.fetchall()]
            
            for table in expected_tables:
                if table in existing_tables:
                    print(f"✅ Table '{db_name}.{table}' exists")
                else:
                    print(f"❌ Table '{db_name}.{table}' missing")
                    all_passed = False
            
            cursor.close()
            conn.close()
            
        except Exception as e:
            print(f"❌ Schema test failed for '{db_name}': {e}")
            all_passed = False
    
    return all_passed

def main():
    """Main test function"""
    print("🧪 Database Connectivity Test Suite")
    print("=" * 50)
    
    # Allow time for containers to start up
    if "--wait" in sys.argv:
        print("⏳ Waiting 10 seconds for containers to start...")
        time.sleep(10)
    
    tests_passed = 0
    total_tests = 4
    
    # Test PostgreSQL connection
    if test_postgres_connection():
        tests_passed += 1
    
    # Test individual databases
    db_results = test_individual_databases()
    if all(db_results.values()):
        tests_passed += 1
    
    # Test Redis connection
    if test_redis_connection():
        tests_passed += 1
    
    # Test database schemas
    if test_database_schemas():
        tests_passed += 1
    
    # Summary
    print("\n" + "=" * 50)
    print(f"📊 Test Results: {tests_passed}/{total_tests} tests passed")
    
    if tests_passed == total_tests:
        print("🎉 All database connectivity tests passed!")
        sys.exit(0)
    else:
        print("❌ Some tests failed. Please check the configuration.")
        sys.exit(1)

if __name__ == "__main__":
    main() 