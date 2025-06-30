# Odoo SaaS Kit - Project Structure

```
odoo-saas-kit/
├── README.md                           # Comprehensive setup and usage guide
├── docker-compose.yml                  # Main development environment (symlink to infrastructure/compose/)
├── .env.example                        # Environment variables template
├── .env                               # Actual environment variables (gitignored)
├── .gitignore                         # Git ignore rules
├── Makefile                           # Common development commands (includes swarm targets)
└── LICENSE                            # Project license

├── infrastructure/                     # Infrastructure and deployment configs
│   ├── traefik/
│   │   ├── traefik.yml                # Traefik static configuration
│   │   ├── traefik-swarm.yml          # Traefik swarm mode configuration
│   │   ├── dynamic/                   # Dynamic configuration files
│   │   │   ├── middlewares.yml        # Auth, CORS, rate limiting
│   │   │   └── tls.yml               # SSL/TLS configuration
│   │   └── Dockerfile                 # Custom Traefik image if needed
│   ├── swarm/                        # Docker Swarm configurations
│   │   ├── docker-stack.yml          # Main swarm stack file
│   │   ├── stacks/                   # Individual service stacks
│   │   │   ├── core-services.yml     # Core SaaS services stack
│   │   │   ├── monitoring.yml        # Monitoring stack for swarm
│   │   │   ├── traefik.yml          # Traefik proxy stack
│   │   │   └── storage.yml          # Storage services stack
│   │   ├── configs/                  # Swarm configs (non-sensitive)
│   │   │   ├── traefik-swarm.yml    # Traefik swarm configuration
│   │   │   ├── prometheus-swarm.yml  # Prometheus swarm configuration
│   │   │   └── redis-swarm.conf     # Redis swarm configuration
│   │   ├── secrets/                  # Swarm secrets templates
│   │   │   ├── secrets.example.yml   # Example secrets file
│   │   │   └── create-secrets.sh    # Script to create swarm secrets
│   │   ├── networks/                 # Swarm network definitions
│   │   │   ├── overlay-networks.yml  # Overlay network configurations
│   │   │   └── network-setup.sh     # Network initialization script
│   │   ├── volumes/                  # Swarm volume configurations
│   │   │   ├── volume-definitions.yml # Persistent volume definitions
│   │   │   └── storage-setup.sh     # Storage initialization script
│   │   └── placement/               # Service placement constraints
│   │       ├── constraints.yml      # Node placement rules
│   │       └── labels.sh           # Node labeling script
│   ├── compose/                     # Docker Compose configurations
│   │   ├── docker-compose.yml       # Development environment
│   │   ├── docker-compose.prod.yml  # Production compose (non-swarm)
│   │   ├── docker-compose.test.yml  # Testing environment
│   │   └── overrides/              # Environment-specific overrides
│   │       ├── development.yml     # Development overrides
│   │       ├── staging.yml         # Staging overrides
│   │       └── production.yml      # Production overrides
│   ├── monitoring/
│   │   ├── prometheus/
│   │   │   ├── prometheus.yml         # Prometheus configuration
│   │   │   ├── prometheus-swarm.yml   # Prometheus swarm configuration
│   │   │   └── alerts.yml            # Alert rules
│   │   ├── grafana/
│   │   │   ├── dashboards/           # Pre-built dashboards
│   │   │   └── provisioning/         # Grafana auto-provisioning
│   │   └── docker-compose.monitoring.yml # Monitoring stack
│   ├── nginx/
│   │   ├── nginx.conf                # Nginx configuration for static assets
│   │   └── Dockerfile                # Custom Nginx image
│   ├── migration/                   # Compose to Swarm migration tools
│   │   ├── compose-to-stack.py      # Convert compose files to stack files
│   │   ├── validate-stack.sh        # Validate stack configurations
│   │   ├── migration-checklist.md   # Pre-migration checklist
│   │   └── rollback.sh             # Rollback from swarm to compose
│   └── scripts/
│       ├── deploy.sh                 # Deployment automation script
│       ├── deploy-swarm.sh          # Swarm deployment script
│       ├── init-swarm.sh            # Initialize swarm cluster
│       ├── backup.sh                # Backup automation script
│       ├── health-check.sh          # System health verification
│       ├── scale-services.sh        # Service scaling script
│       └── update-services.sh       # Rolling update script

├── services/                          # All microservices
│   ├── web-app/                      # Flask frontend application
│   │   ├── app/
│   │   │   ├── __init__.py           # Flask app factory
│   │   │   ├── routes/               # Route blueprints
│   │   │   │   ├── __init__.py
│   │   │   │   ├── auth.py          # Authentication routes
│   │   │   │   ├── dashboard.py     # User dashboard
│   │   │   │   ├── instances.py     # Instance management
│   │   │   │   └── billing.py       # Billing interface
│   │   │   ├── templates/            # Jinja2 templates
│   │   │   │   ├── base.html        # Base template
│   │   │   │   ├── auth/            # Authentication pages
│   │   │   │   ├── dashboard/       # Dashboard pages
│   │   │   │   └── billing/         # Billing pages
│   │   │   ├── static/              # CSS, JS, images
│   │   │   │   ├── css/
│   │   │   │   ├── js/
│   │   │   │   └── img/
│   │   │   └── utils/               # Utility functions
│   │   │       ├── __init__.py
│   │   │       ├── auth_helpers.py  # Authentication utilities
│   │   │       └── api_client.py    # API communication helpers
│   │   ├── config/
│   │   │   ├── __init__.py
│   │   │   ├── development.py       # Development configuration
│   │   │   ├── production.py        # Production configuration
│   │   │   └── testing.py           # Testing configuration
│   │   ├── tests/                   # Test applications
│   │   │   ├── test_auth_app.py     # Authentication testing app
│   │   │   ├── test_dashboard_app.py # Dashboard testing app
│   │   │   └── test_integration_app.py # Integration testing app
│   │   ├── requirements.txt         # Python dependencies
│   │   ├── Dockerfile              # Web app container
│   │   ├── .env.example            # Web app environment template
│   │   └── wsgi.py                 # WSGI entry point
│   │
│   ├── user-service/                # User management microservice
│   │   ├── app/
│   │   │   ├── __init__.py         # FastAPI app initialization
│   │   │   ├── models/             # Pydantic models
│   │   │   │   ├── __init__.py
│   │   │   │   ├── user.py         # User data models
│   │   │   │   └── auth.py         # Authentication models
│   │   │   ├── routers/            # API route handlers
│   │   │   │   ├── __init__.py
│   │   │   │   ├── auth.py         # Authentication endpoints
│   │   │   │   ├── users.py        # User management endpoints
│   │   │   │   └── profile.py      # User profile endpoints
│   │   │   ├── services/           # Business logic
│   │   │   │   ├── __init__.py
│   │   │   │   ├── auth_service.py # Authentication logic
│   │   │   │   ├── user_service.py # User management logic
│   │   │   │   └── supabase_client.py # Supabase integration
│   │   │   └── utils/              # Utility functions
│   │   │       ├── __init__.py
│   │   │       ├── security.py     # JWT, hashing utilities
│   │   │       └── validators.py   # Input validation
│   │   ├── config/                 # Configuration management
│   │   │   ├── __init__.py
│   │   │   └── settings.py         # Environment-based settings
│   │   ├── tests/                  # Test applications
│   │   │   ├── test_auth_endpoints.py # Auth testing app
│   │   │   ├── test_user_crud.py   # User CRUD testing app
│   │   │   └── test_supabase_integration.py # DB testing app
│   │   ├── requirements.txt        # Python dependencies
│   │   ├── Dockerfile             # User service container
│   │   └── .env.example           # Environment template
│   │
│   ├── instance-service/           # Odoo instance provisioning service
│   │   ├── app/
│   │   │   ├── __init__.py        # FastAPI app initialization
│   │   │   ├── models/            # Data models
│   │   │   │   ├── __init__.py
│   │   │   │   ├── instance.py    # Instance data models
│   │   │   │   └── odoo_config.py # Odoo configuration models
│   │   │   ├── routers/           # API endpoints
│   │   │   │   ├── __init__.py
│   │   │   │   ├── instances.py   # Instance management
│   │   │   │   ├── provisioning.py # Instance provisioning
│   │   │   │   └── monitoring.py  # Instance health monitoring
│   │   │   ├── services/          # Core business logic
│   │   │   │   ├── __init__.py
│   │   │   │   ├── instance_manager.py # Instance lifecycle
│   │   │   │   ├── docker_manager.py # Docker operations
│   │   │   │   ├── postgres_manager.py # DB provisioning
│   │   │   │   └── backup_manager.py # Backup operations
│   │   │   └── templates/         # Odoo configuration templates
│   │   │       ├── odoo.conf.j2   # Odoo config template
│   │   │       └── docker-compose.instance.yml.j2
│   │   ├── odoo-versions/         # Odoo version configurations
│   │   │   ├── v17/              # Odoo 17 configs
│   │   │   ├── v16/              # Odoo 16 configs
│   │   │   ├── v15/              # Odoo 15 configs
│   │   │   └── v14/              # Odoo 14 configs
│   │   ├── tests/                # Test applications
│   │   │   ├── test_provisioning.py # Instance provisioning tests
│   │   │   ├── test_docker_ops.py # Docker operations tests
│   │   │   └── test_backup_restore.py # Backup/restore tests
│   │   ├── requirements.txt      # Python dependencies
│   │   ├── Dockerfile           # Instance service container
│   │   └── .env.example         # Environment template
│   │
│   ├── billing-service/          # Payment and billing microservice
│   │   ├── app/
│   │   │   ├── __init__.py      # FastAPI app initialization
│   │   │   ├── models/          # Data models
│   │   │   │   ├── __init__.py
│   │   │   │   ├── billing.py   # Billing data models
│   │   │   │   ├── payment.py   # Payment models
│   │   │   │   └── subscription.py # Subscription models
│   │   │   ├── routers/         # API endpoints
│   │   │   │   ├── __init__.py
│   │   │   │   ├── billing.py   # Billing management
│   │   │   │   ├── payments.py  # Payment processing
│   │   │   │   └── subscriptions.py # Subscription management
│   │   │   ├── services/        # Business logic
│   │   │   │   ├── __init__.py
│   │   │   │   ├── billing_service.py # Billing calculations
│   │   │   │   ├── payment_gateways/ # Payment integrations
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── paynow.py    # PayNow integration
│   │   │   │   │   ├── ecocash.py   # EcoCash integration
│   │   │   │   │   └── onemoney.py  # OneMoney integration
│   │   │   │   └── subscription_service.py # Subscription logic
│   │   │   └── utils/           # Utility functions
│   │   │       ├── __init__.py
│   │   │       └── currency.py  # Currency utilities
│   │   ├── tests/              # Test applications
│   │   │   ├── test_billing.py # Billing logic tests
│   │   │   ├── test_payments.py # Payment processing tests
│   │   │   └── test_gateways.py # Payment gateway tests
│   │   ├── requirements.txt    # Python dependencies
│   │   ├── Dockerfile         # Billing service container
│   │   └── .env.example       # Environment template
│   │
│   ├── notification-service/   # Email and notification service
│   │   ├── app/
│   │   │   ├── __init__.py    # FastAPI app initialization
│   │   │   ├── models/        # Data models
│   │   │   │   ├── __init__.py
│   │   │   │   └── notification.py # Notification models
│   │   │   ├── routers/       # API endpoints
│   │   │   │   ├── __init__.py
│   │   │   │   ├── email.py   # Email sending endpoints
│   │   │   │   └── notifications.py # Notification management
│   │   │   ├── services/      # Business logic
│   │   │   │   ├── __init__.py
│   │   │   │   ├── email_service.py # Email sending logic
│   │   │   │   └── template_service.py # Template management
│   │   │   └── templates/     # Email templates
│   │   │       ├── welcome.html # Welcome email
│   │   │       ├── instance_ready.html # Instance ready notification
│   │   │       ├── billing_reminder.html # Billing reminders
│   │   │       └── system_alert.html # System alerts
│   │   ├── tests/            # Test applications
│   │   │   ├── test_email.py # Email sending tests
│   │   │   └── test_templates.py # Template rendering tests
│   │   ├── requirements.txt  # Python dependencies
│   │   ├── Dockerfile       # Notification service container
│   │   └── .env.example     # Environment template
│   │
│   └── admin-service/        # Admin dashboard and management
│       ├── app/
│       │   ├── __init__.py   # FastAPI app initialization
│       │   ├── models/       # Data models
│       │   │   ├── __init__.py
│       │   │   └── admin.py  # Admin data models
│       │   ├── routers/      # API endpoints
│       │   │   ├── __init__.py
│       │   │   ├── dashboard.py # Admin dashboard data
│       │   │   ├── users.py    # User management
│       │   │   ├── instances.py # Instance management
│       │   │   └── system.py   # System management
│       │   ├── services/     # Business logic
│       │   │   ├── __init__.py
│       │   │   ├── analytics_service.py # Usage analytics
│       │   │   └── system_service.py # System management
│       │   └── utils/        # Utility functions
│       │       ├── __init__.py
│       │       └── permissions.py # Admin permissions
│       ├── tests/           # Test applications
│       │   ├── test_dashboard.py # Dashboard tests
│       │   └── test_permissions.py # Permission tests
│       ├── requirements.txt # Python dependencies
│       ├── Dockerfile      # Admin service container
│       └── .env.example    # Environment template

├── shared/                  # Shared utilities and configurations
│   ├── configs/            # Shared configuration files
│   │   ├── redis.conf     # Redis configuration
│   │   └── logging.yml    # Logging configuration
│   ├── utils/             # Shared utility functions
│   │   ├── __init__.py
│   │   ├── database.py    # Database utilities
│   │   ├── redis_client.py # Redis client
│   │   ├── logger.py      # Logging utilities
│   │   └── security.py    # Security utilities
│   └── schemas/           # Shared data schemas
│       ├── __init__.py
│       ├── user.py        # User schemas
│       ├── instance.py    # Instance schemas
│       └── billing.py     # Billing schemas

├── docs/                   # Documentation
│   ├── DEPLOYMENT.md      # Deployment guide
│   ├── API.md             # API documentation
│   ├── ARCHITECTURE.md    # Architecture overview
│   ├── TESTING.md         # Testing guide
│   ├── MONITORING.md      # Monitoring setup
│   └── TROUBLESHOOTING.md # Common issues and fixes

└── scripts/               # Development and deployment scripts
    ├── dev-setup.sh       # Development environment setup
    ├── test-runner.sh     # Run all test applications
    ├── build-all.sh       # Build all Docker images
    ├── deploy-compose.sh  # Deploy with Docker Compose
    ├── deploy-swarm.sh    # Deploy to Docker Swarm
    ├── swarm-init.sh      # Initialize Docker Swarm cluster
    ├── swarm-join.sh      # Join nodes to swarm
    ├── migrate-to-swarm.sh # Migrate from compose to swarm
    ├── scale-services.sh  # Scale swarm services
    └── cleanup.sh         # Clean up development environment
```

## Key Structure Principles

**Microservices Separation**: Each service is completely independent with its own dependencies, configuration, and testing.

**Dual Deployment Support**: 
- **Development**: Docker Compose (`infrastructure/compose/`) for rapid development and testing
- **Production**: Docker Swarm (`infrastructure/swarm/`) for scalable, distributed deployment

**Migration Path**: Clear migration tools and scripts to move from Compose to Swarm with validation and rollback capabilities.

**Configuration Management**: Environment-based configuration with `.env` files and no hardcoded values. Swarm uses Docker secrets and configs for sensitive data.

**Storage Strategy**: 
- **Compose**: Local volumes and bind mounts
- **Swarm**: Shared storage with volume management and Contabo backup integration

**Testing Strategy**: Test applications instead of test scripts - practical testing that mirrors real usage.

**Documentation**: Comprehensive documentation for deployment, API usage, and troubleshooting.

**Infrastructure as Code**: All infrastructure configuration in version control with Traefik, monitoring, and deployment automation for both modes.

**Scalability**: Structure supports horizontal scaling in Docker Swarm with service placement constraints and replica management.

**Security**: Proper separation of concerns, environment-based secrets in Compose, Docker secrets in Swarm, and security utilities.

**Simplicity**: Clear, logical structure without over-complication while maintaining all necessary SaaS features and deployment flexibility.

**Curl command** to register webook link
curl -u admin:password -X POST
  "http://localhost:8081/1.0/kb/tenants/uploadPerTenantConfig" \
    -H "Content-Type: text/plain" \
    -H "X-Killbill-ApiKey: test-key" \
    -H "X-Killbill-ApiSecret: test-secret" \
    -H "X-Killbill-CreatedBy: admin" \
    -d 'org.killbill.billing.server.notifications.url=http://billing-se
  rvice:8004/api/billing/webhooks/killbill'