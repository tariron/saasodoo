# pgAdmin Database Management Guide

## Overview

pgAdmin 4 is included in your SaaSOdoo development environment to provide a web-based interface for managing PostgreSQL databases. It comes pre-configured with all your project databases.

## Accessing pgAdmin

### URL Access
- **Development URL**: `http://pgadmin.saasodoo.local`
- **Login Credentials**:
  - Email: `admin@saasodoo.local`
  - Password: `pgadmin_password_change_me` (change this in your `.env` file)

### Using Makefile Commands
```bash
# Open pgAdmin in your default browser
make pgadmin-open

# View pgAdmin logs
make pgadmin-logs

# Reset pgAdmin (clears all saved connections and preferences)
make pgadmin-reset
```

## Pre-configured Database Connections

pgAdmin comes with the following databases pre-configured:

### SaaSOdoo Development Group
- **SaaSOdoo Main Database**
  - Database: `postgres` (maintenance DB)
  - User: `odoo_user`

### SaaSOdoo Microservices Group
- **Auth Database**
  - Database: `auth`
  - User: `auth_service_user`

- **Billing Database**
  - Database: `billing`
  - User: `billing_service_user`

- **Tenant Database**
  - Database: `tenant`
  - User: `tenant_service_user`

- **Communication Database**
  - Database: `communication`
  - User: `postgres`

- **Analytics Database**
  - Database: `analytics`
  - User: `postgres`

## First-Time Setup

1. **Start the services**:
   ```bash
   make dev-up
   ```

2. **Access pgAdmin**:
   ```bash
   make pgadmin-open
   ```

3. **Connect to databases**:
   - All server connections are pre-configured
   - You'll need to enter passwords for each connection when you first access them
   - Passwords are defined in your `.env` file

## Common Tasks

### Viewing Database Schema
1. Expand the server in the left panel
2. Navigate to: `Databases` → `[database_name]` → `Schemas` → `public` → `Tables`
3. Right-click on any table to view data or properties

### Running SQL Queries
1. Right-click on a database
2. Select `Query Tool`
3. Write your SQL and click the play button

### Managing Users and Permissions
1. Expand `Login/Group Roles` under a server
2. Right-click to create new roles or modify existing ones

### Database Backup and Restore
1. Right-click on a database
2. Select `Backup...` or `Restore...`
3. Configure options and execute

## Security Notes

⚠️ **Development Environment Only**
- The current configuration is for development only
- In production, use stronger passwords and enable SSL
- Consider restricting network access

## Troubleshooting

### Can't Connect to pgAdmin
```bash
# Check if pgAdmin is running
docker ps | grep pgadmin

# View pgAdmin logs
make pgadmin-logs

# Restart pgAdmin
docker-compose -f infrastructure/compose/docker-compose.dev.yml restart pgadmin
```

### Database Connection Failures
1. Verify PostgreSQL is running: `docker ps | grep postgres`
2. Check database credentials in `.env` file
3. Ensure the database exists: `make db-test`

### Lost pgAdmin Configuration
```bash
# Reset pgAdmin (will lose saved connections and preferences)
make pgadmin-reset
```

## Configuration Files

- **Docker Compose**: `infrastructure/compose/docker-compose.dev.yml`
- **Server Configuration**: `shared/configs/pgadmin/servers.json`
- **Environment Variables**: `.env`

## Customization

### Adding New Database Connections
1. Edit `shared/configs/pgadmin/servers.json`
2. Add new server configuration
3. Restart pgAdmin: `make pgadmin-reset`

### Changing pgAdmin Settings
Modify these environment variables in your `.env` file:
- `PGADMIN_DEFAULT_EMAIL`: Login email
- `PGADMIN_DEFAULT_PASSWORD`: Login password

## URLs Summary

| Service | URL | Purpose |
|---------|-----|---------|
| pgAdmin | http://pgadmin.saasodoo.local | Database management interface |
| PostgreSQL | localhost:5432 | Direct database access |
| Traefik | http://traefik.saasodoo.local | Reverse proxy dashboard |

## Related Commands

```bash
# Database testing
make db-test

# Database reset
make db-reset

# View all services
make dev-ps

# View all logs
make dev-logs
``` 