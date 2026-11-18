-- Rocket Genie HRMS
-- Creates the new PostgreSQL database requested for HR records.
-- Run this file from psql while connected to a maintenance database
-- such as "postgres".
--
-- Exact database name:
--     Robo Gini HR Records
--
-- psql is required because CREATE DATABASE cannot run inside a transaction.

SELECT 'CREATE DATABASE "Robo Gini HR Records" OWNER rocket'
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_database
    WHERE datname = 'Robo Gini HR Records'
)\gexec

\connect "Robo Gini HR Records"

-- Make sure the application role can use the database/schema.
GRANT CONNECT ON DATABASE "Robo Gini HR Records" TO rocket;
GRANT USAGE, CREATE ON SCHEMA public TO rocket;
