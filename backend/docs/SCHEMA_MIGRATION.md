# Schema Migration: `_realtime` → `_fd`

## Problem

`_realtime` is a reserved Supabase schema. Creating tables in it fails with:
```
ERROR: cannot create table in reserved schema "_realtime"
```

## Solution

Use `_fd` schema instead.
## fd stands for fairdatabase

## Schema Structure

### System Tables
- `_fd.metadata_tables` - Tracks uploaded datasets
- `_fd.sample_metadata` - Stores sample metadata

### Data Tables
- `_fd.{filename}_p{chunk}` - User-uploaded data (auto-created)

## Migration

### Fresh Installation
No action needed. Schema creates automatically on first data upload.

### Existing Installation (if migrating)
See `migrate_schema.sql`

## Schema Initialization

Function: `pg_ensure_schema_and_metadata()` in `src/dashboard/helpers.py`

Called automatically during first data upload.
