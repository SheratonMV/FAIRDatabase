-- Enable pgTAP extension for database testing
-- This must be run before any tests can be executed

CREATE EXTENSION IF NOT EXISTS pgtap WITH SCHEMA public;
