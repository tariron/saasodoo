"""
SaaSOdoo Capacity Load Tests

Real end-to-end load testing including:
- User registration (creates real KillBill accounts)
- Authentication flow (login/logout)
- API throughput testing

Usage:
    # Web UI mode
    locust -f locustfile.py --host=http://api.109.199.108.243.nip.io

    # Headless mode (100 users, 10 users/sec spawn rate, 5 min run)
    locust -f locustfile.py --host=http://api.109.199.108.243.nip.io \
        --headless -u 100 -r 10 -t 5m

    # User registration only
    locust -f locustfile.py --host=http://api.109.199.108.243.nip.io \
        --headless -u 50 -r 5 -t 2m --tags registration
"""

import random
import string
import time
import uuid
from locust import HttpUser, task, between, tag, events
from locust.runners import MasterRunner, WorkerRunner


# Test configuration
class Config:
    # API paths
    USER_SERVICE_PREFIX = "/user"
    BILLING_SERVICE_PREFIX = "/billing"
    INSTANCE_SERVICE_PREFIX = "/instance"

    # Password that meets requirements (uppercase, lowercase, digit, special)
    DEFAULT_PASSWORD = "LoadTest123@"

    # Domain for generated emails
    EMAIL_DOMAIN = "loadtest.saasodoo.com"

    # Countries for random selection
    COUNTRIES = ["US", "UK", "DE", "FR", "CA", "AU", "NL", "BE", "CH", "AT"]

    # Companies for random selection
    COMPANIES = [
        "Acme Corp", "TechStart", "GlobalTech", "DataDriven",
        "CloudFirst", "InnovateCo", "DigitalEdge", "SmartBiz"
    ]


def generate_unique_email():
    """Generate a unique email address for testing."""
    timestamp = int(time.time() * 1000)
    random_suffix = ''.join(random.choices(string.ascii_lowercase, k=6))
    return f"user_{timestamp}_{random_suffix}@{Config.EMAIL_DOMAIN}"


def generate_phone():
    """Generate a random phone number."""
    return f"+1{random.randint(2000000000, 9999999999)}"


def generate_first_name():
    """Generate a random first name."""
    names = ["John", "Jane", "Mike", "Sarah", "David", "Emma", "Chris", "Lisa",
             "Alex", "Maria", "James", "Anna", "Robert", "Laura", "Daniel", "Sofia"]
    return random.choice(names)


def generate_last_name():
    """Generate a random last name."""
    names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
             "Davis", "Rodriguez", "Martinez", "Wilson", "Anderson", "Taylor", "Thomas"]
    return random.choice(names)


class RegistrationUser(HttpUser):
    """
    User that registers new accounts.

    This creates REAL users in the database and REAL KillBill accounts.
    Use for capacity testing of the registration pipeline.
    """

    wait_time = between(1, 3)  # Wait 1-3 seconds between tasks

    # Track registered users for potential follow-up tests
    registered_users = []

    @tag("registration", "user-creation")
    @task(1)
    def register_new_user(self):
        """Register a new user - creates real DB and KillBill accounts."""

        email = generate_unique_email()
        payload = {
            "email": email,
            "password": Config.DEFAULT_PASSWORD,
            "first_name": generate_first_name(),
            "last_name": generate_last_name(),
            "phone": generate_phone(),
            "company": random.choice(Config.COMPANIES),
            "country": random.choice(Config.COUNTRIES),
            "accept_terms": True,
            "marketing_consent": random.choice([True, False])
        }

        with self.client.post(
            f"{Config.USER_SERVICE_PREFIX}/auth/register",
            json=payload,
            name="Register User",
            catch_response=True
        ) as response:
            if response.status_code == 201:
                data = response.json()
                if data.get("success"):
                    # Store for potential follow-up tests
                    self.registered_users.append({
                        "email": email,
                        "password": Config.DEFAULT_PASSWORD,
                        "customer_id": data.get("customer", {}).get("id")
                    })
                    response.success()
                else:
                    response.failure(f"Registration failed: {data}")
            elif response.status_code == 409:
                # Email already exists (unlikely with our unique generation)
                response.failure("Email already exists")
            else:
                response.failure(f"Status {response.status_code}: {response.text}")


class AuthenticationUser(HttpUser):
    """
    User that tests authentication flow with pre-existing accounts.

    Use this to test login/logout throughput without creating new accounts.
    Requires TEST_USERS environment variable or will create its own user first.
    """

    wait_time = between(0.5, 2)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.email = None
        self.password = Config.DEFAULT_PASSWORD
        self.token = None
        self.customer_id = None

    def on_start(self):
        """Create a test user on start (if needed)."""
        # Register a user for this session
        email = generate_unique_email()
        payload = {
            "email": email,
            "password": self.password,
            "first_name": generate_first_name(),
            "last_name": generate_last_name(),
            "accept_terms": True
        }

        response = self.client.post(
            f"{Config.USER_SERVICE_PREFIX}/auth/register",
            json=payload,
            name="Setup: Register User"
        )

        if response.status_code == 201:
            data = response.json()
            self.email = email
            self.customer_id = data.get("customer", {}).get("id")
        else:
            # Failed to create user, this session won't work
            self.email = None

    @tag("auth", "login")
    @task(3)
    def login(self):
        """Test login endpoint."""
        if not self.email:
            return

        payload = {
            "email": self.email,
            "password": self.password,
            "remember_me": False
        }

        with self.client.post(
            f"{Config.USER_SERVICE_PREFIX}/auth/login",
            json=payload,
            name="Login",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    self.token = data.get("tokens", {}).get("access_token")
                    response.success()
                else:
                    response.failure(f"Login failed: {data.get('error')}")
            else:
                response.failure(f"Status {response.status_code}")

    @tag("auth", "session")
    @task(5)
    def get_current_user(self):
        """Test session validation (GET /auth/me)."""
        if not self.token:
            return

        headers = {"Authorization": f"Bearer {self.token}"}

        with self.client.get(
            f"{Config.USER_SERVICE_PREFIX}/auth/me",
            headers=headers,
            name="Get Current User",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 401:
                # Token expired or invalid, need to login again
                self.token = None
                response.failure("Token expired")
            else:
                response.failure(f"Status {response.status_code}")

    @tag("auth", "logout")
    @task(1)
    def logout(self):
        """Test logout endpoint."""
        if not self.token:
            return

        headers = {"Authorization": f"Bearer {self.token}"}

        with self.client.post(
            f"{Config.USER_SERVICE_PREFIX}/auth/logout",
            headers=headers,
            name="Logout",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                self.token = None
                response.success()
            else:
                response.failure(f"Status {response.status_code}")


class HealthCheckUser(HttpUser):
    """
    Baseline health check testing.

    Use this to establish baseline throughput and latency.
    """

    wait_time = between(0.1, 0.5)  # Fast polling

    @tag("health", "baseline")
    @task(3)
    def health_check(self):
        """Simple health check."""
        self.client.get(
            f"{Config.USER_SERVICE_PREFIX}/health",
            name="Health Check"
        )

    @tag("health", "database")
    @task(1)
    def health_database(self):
        """Database health check."""
        self.client.get(
            f"{Config.USER_SERVICE_PREFIX}/health/database",
            name="Health Check (DB)"
        )


class MixedWorkloadUser(HttpUser):
    """
    Mixed workload simulating real usage patterns.

    Weights approximate real-world usage:
    - 5% new registrations
    - 30% logins
    - 50% authenticated requests
    - 10% logouts
    - 5% health checks
    """

    wait_time = between(1, 5)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.email = None
        self.password = Config.DEFAULT_PASSWORD
        self.token = None

    @tag("mixed", "registration")
    @task(1)
    def register(self):
        """Occasional new user registration."""
        email = generate_unique_email()
        payload = {
            "email": email,
            "password": self.password,
            "first_name": generate_first_name(),
            "last_name": generate_last_name(),
            "accept_terms": True
        }

        with self.client.post(
            f"{Config.USER_SERVICE_PREFIX}/auth/register",
            json=payload,
            name="[Mixed] Register",
            catch_response=True
        ) as response:
            if response.status_code == 201:
                self.email = email
                response.success()

    @tag("mixed", "auth")
    @task(6)
    def login_session_logout_cycle(self):
        """Full auth cycle."""
        if not self.email:
            # Need to register first
            self.register()
            return

        # Login
        login_resp = self.client.post(
            f"{Config.USER_SERVICE_PREFIX}/auth/login",
            json={"email": self.email, "password": self.password},
            name="[Mixed] Login"
        )

        if login_resp.status_code != 200:
            return

        token = login_resp.json().get("tokens", {}).get("access_token")
        if not token:
            return

        headers = {"Authorization": f"Bearer {token}"}

        # Get profile (simulating user activity)
        self.client.get(
            f"{Config.USER_SERVICE_PREFIX}/auth/me",
            headers=headers,
            name="[Mixed] Get Profile"
        )

        # 50% chance to logout
        if random.random() > 0.5:
            self.client.post(
                f"{Config.USER_SERVICE_PREFIX}/auth/logout",
                headers=headers,
                name="[Mixed] Logout"
            )

    @tag("mixed", "health")
    @task(1)
    def health(self):
        """Background health monitoring."""
        self.client.get(
            f"{Config.USER_SERVICE_PREFIX}/health",
            name="[Mixed] Health"
        )


# Event handlers for reporting
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when test starts."""
    if isinstance(environment.runner, MasterRunner):
        print("=" * 60)
        print("SaaSOdoo Capacity Load Test Starting")
        print("=" * 60)
        print(f"Target host: {environment.host}")
        print("WARNING: This creates REAL users and KillBill accounts!")
        print("=" * 60)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when test stops."""
    if isinstance(environment.runner, MasterRunner):
        print("=" * 60)
        print("Load Test Complete")
        print("=" * 60)
