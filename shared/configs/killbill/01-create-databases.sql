-- MySQL Database Initialization for KillBill and Kaui
-- This script creates the necessary databases for KillBill ecosystem

-- Create Kaui database (KillBill database is created via MYSQL_DATABASE env var)
CREATE DATABASE IF NOT EXISTS kaui;

-- Grant permissions to the KillBill user for both databases
GRANT ALL PRIVILEGES ON killbill.* TO 'killbill'@'%';
GRANT ALL PRIVILEGES ON kaui.* TO 'killbill'@'%';

-- Flush privileges to ensure they take effect
FLUSH PRIVILEGES;

-- Display created databases
SHOW DATABASES;