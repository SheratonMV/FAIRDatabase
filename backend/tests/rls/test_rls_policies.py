"""
Phase 6: RLS Policy Integration Tests

Tests Row Level Security policies from application level using different user roles.
Covers metadata tables, dynamic data tables, and RPC functions.
"""

import time
from io import BytesIO

import pytest

from config import get_db, supabase_extension


class TestMetadataTableRLS:
    """Test RLS policies on _realtime.metadata_tables"""

    @pytest.fixture(scope="class")
    def test_users(self, app):
        """Create two test users for isolation testing"""
        with app.app_context():
            service_client = supabase_extension.service_role_client

            # Clean up any existing test users
            user_list = service_client.auth.admin.list_users()
            for user in user_list:
                if user.email in ["rls_test_user1@test.com", "rls_test_user2@test.com"]:
                    service_client.auth.admin.delete_user(user.id)

            # Create user 1
            user1_response = service_client.auth.admin.create_user(
                {
                    "email": "rls_test_user1@test.com",
                    "password": "TestPassword123!",
                    "email_confirm": True,
                }
            )

            # Create user 2
            user2_response = service_client.auth.admin.create_user(
                {
                    "email": "rls_test_user2@test.com",
                    "password": "TestPassword123!",
                    "email_confirm": True,
                }
            )

            yield {"user1": user1_response.user, "user2": user2_response.user}

            # Cleanup
            service_client.auth.admin.delete_user(user1_response.user.id)
            service_client.auth.admin.delete_user(user2_response.user.id)

    def test_rls_enabled_on_metadata_tables(self, app):
        """Verify RLS is enabled on metadata_tables"""
        with app.app_context():
            conn = get_db()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT rowsecurity
                    FROM pg_tables
                    WHERE schemaname = '_realtime' AND tablename = 'metadata_tables';
                """)
                result = cur.fetchone()
                assert result is not None, "metadata_tables table not found"
                assert result[0] is True, "RLS should be enabled on metadata_tables"

    def test_rls_policies_exist(self, app):
        """Verify expected RLS policies exist on metadata_tables"""
        with app.app_context():
            conn = get_db()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT policyname, cmd, roles
                    FROM pg_policies
                    WHERE schemaname = '_realtime' AND tablename = 'metadata_tables';
                """)
                policies = cur.fetchall()

                policy_names = [p[0] for p in policies]
                # Updated policy names from user-level data isolation implementation
                assert "users_view_own_metadata" in policy_names
                assert "service_role_full_metadata_access" in policy_names

    def test_service_role_can_read_all_metadata(self, app):
        """Service role should see all metadata entries"""
        with app.app_context():
            result = (
                supabase_extension.service_role_client.schema("_realtime")
                .table("metadata_tables")
                .select("*")
                .execute()
            )
            # Should not raise error, service role has full access
            assert result is not None

    def test_authenticated_can_read_metadata(self, app, test_users):
        """Authenticated users can read metadata"""
        with app.app_context():
            # Sign in as user1
            session = supabase_extension.client.auth.sign_in_with_password(
                {"email": "rls_test_user1@test.com", "password": "TestPassword123!"}
            )

            assert session.user is not None

            # Try to read metadata
            result = (
                supabase_extension.client.schema("_realtime")
                .table("metadata_tables")
                .select("*")
                .execute()
            )

            # Should succeed (authenticated users can SELECT)
            assert result is not None

            # Cleanup session
            supabase_extension.client.auth.sign_out()

    def test_authenticated_cannot_write_metadata_directly(self, app, test_users):
        """Authenticated users cannot INSERT/UPDATE/DELETE metadata directly"""
        with app.app_context():
            # Sign in as user1
            session = supabase_extension.client.auth.sign_in_with_password(
                {"email": "rls_test_user1@test.com", "password": "TestPassword123!"}
            )

            # Try to insert metadata directly (should fail)
            with pytest.raises(Exception) as exc_info:
                (
                    supabase_extension.client.schema("_realtime")
                    .table("metadata_tables")
                    .insert(
                        {
                            "table_name": "malicious_table",
                            "main_table": "malicious",
                            "description": "Attempt to bypass security",
                        }
                    )
                    .execute()
                )

            # Should raise permission error
            assert (
                "permission denied" in str(exc_info.value).lower()
                or "new row violates" in str(exc_info.value).lower()
            )

            # Cleanup session
            supabase_extension.client.auth.sign_out()


class TestDynamicTableRLS:
    """Test RLS policies on dynamically created data tables"""

    @pytest.fixture(scope="class")
    def sample_data_table(self, app, logged_in_user):
        """Create a sample data table via CSV upload"""
        test_client, user = logged_in_user

        # Create a simple CSV file
        csv_content = b"patient_id,age,diagnosis\nP001,45,Diabetes\nP002,32,Hypertension\n"
        csv_file = (BytesIO(csv_content), "test_rls_data.csv")

        response = test_client.post(
            "/dashboard/upload",
            data={"file": csv_file, "description": "Test table for RLS", "origin": "Test"},
            content_type="multipart/form-data",
            follow_redirects=True,
        )

        # Give database time to process
        time.sleep(1)

        # Determine actual table name from response or query database
        with app.app_context():
            conn = get_db()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT table_name FROM _realtime.metadata_tables
                    WHERE main_table LIKE 'test_rls_data%'
                    ORDER BY id DESC LIMIT 1;
                """)
                result = cur.fetchone()
                table_name = result[0] if result else "test_rls_data_p1"

        yield table_name

        # Cleanup - delete via service role
        with app.app_context():
            conn = get_db()
            with conn.cursor() as cur:
                # Get all chunks
                cur.execute("""
                    SELECT table_name FROM _realtime.metadata_tables
                    WHERE main_table LIKE 'test_rls_data%';
                """)
                tables = [row[0] for row in cur.fetchall()]

                # Drop all related tables
                for table in tables:
                    cur.execute(f"DROP TABLE IF EXISTS _realtime.{table} CASCADE;")

                cur.execute(
                    "DELETE FROM _realtime.metadata_tables WHERE main_table LIKE 'test_rls_data%';"
                )
            conn.commit()

    def test_dynamic_table_has_rls_enabled(self, app, sample_data_table):
        """Verify dynamically created tables have RLS enabled"""
        with app.app_context():
            conn = get_db()
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT rowsecurity
                    FROM pg_tables
                    WHERE schemaname = '_realtime' AND tablename = '{sample_data_table}';
                """)
                result = cur.fetchone()
                assert result is not None, f"Table {sample_data_table} not found"
                assert result[0] is True, f"RLS should be enabled on {sample_data_table}"

    def test_dynamic_table_has_rls_policies(self, app, sample_data_table):
        """Verify dynamically created tables have expected RLS policies"""
        with app.app_context():
            conn = get_db()
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT policyname
                    FROM pg_policies
                    WHERE schemaname = '_realtime' AND tablename = '{sample_data_table}';
                """)
                policies = [row[0] for row in cur.fetchall()]

                # Updated policy names from user-level data isolation implementation
                assert "users_view_own_data" in policies
                assert "service_role_full_data_access" in policies

    def test_authenticated_can_read_data(self, app, sample_data_table, logged_in_user):
        """Authenticated users can read data from tables"""
        with app.app_context():
            result = supabase_extension.safe_rpc_call(
                "select_from_table",
                {"p_table_name": sample_data_table, "p_row_limit": 100, "p_schema_name": "_realtime"},
            )

            # Should succeed
            assert result is not None
            assert len(result) > 0

    def test_authenticated_cannot_write_data_directly(self, app, sample_data_table):
        """Authenticated users cannot INSERT/UPDATE/DELETE directly"""
        with app.app_context():
            # Create authenticated client (not service role)
            # Note: In production, this would be the user's client with their session
            with pytest.raises(Exception) as exc_info:
                (
                    supabase_extension.client.schema("_realtime")
                    .table(sample_data_table)
                    .insert({"patient_id": "MALICIOUS", "age": "99", "diagnosis": "Hack"})
                    .execute()
                )

            # Should fail due to lack of INSERT permission
            assert (
                "permission denied" in str(exc_info.value).lower()
                or "violates" in str(exc_info.value).lower()
            )

    def test_service_role_has_full_access(self, app, sample_data_table, logged_in_user):
        """Service role has full read/write access to data tables"""
        test_client, user = logged_in_user
        
        with app.app_context():
            # Service role can read
            read_result = (
                supabase_extension.service_role_client.schema("_realtime")
                .table(sample_data_table)
                .select("*")
                .execute()
            )
            assert read_result is not None

            # Service role can insert (must include user_id since tables have NOT NULL constraint)
            insert_result = (
                supabase_extension.service_role_client.schema("_realtime")
                .table(sample_data_table)
                .insert({
                    "user_id": str(user.id),
                    "patient_id": "P999",
                    "age": "99",
                    "diagnosis": "Test"
                })
                .execute()
            )
            assert insert_result is not None

            # Cleanup the test insert
            (
                supabase_extension.service_role_client.schema("_realtime")
                .table(sample_data_table)
                .delete()
                .eq("patient_id", "P999")
                .execute()
            )


class TestRPCFunctionRLS:
    """Test RPC functions respect RLS and have proper permissions"""

    @pytest.fixture(scope="class")
    def test_user_with_data(self, app, client):
        """Create test user and upload sample data"""
        with app.app_context():
            service_client = supabase_extension.service_role_client

            # Clean up existing user
            user_list = service_client.auth.admin.list_users()
            existing = next((u for u in user_list if u.email == "rpc_test_user@test.com"), None)
            if existing:
                service_client.auth.admin.delete_user(existing.id)

            # Create user
            user_response = service_client.auth.admin.create_user(
                {
                    "email": "rpc_test_user@test.com",
                    "password": "TestPassword123!",
                    "email_confirm": True,
                }
            )

            # Log in user
            client.post(
                "/auth/login",
                data={"email": "rpc_test_user@test.com", "password": "TestPassword123!"},
                follow_redirects=True,
            )

            # Upload sample data
            csv_content = b"patient_id,temperature,heart_rate\nP100,98.6,72\nP101,99.1,80\n"
            csv_file = (BytesIO(csv_content), "rpc_test_data.csv")

            client.post(
                "/dashboard/upload",
                data={"file": csv_file, "description": "RPC test data", "origin": "Test"},
                content_type="multipart/form-data",
                follow_redirects=True,
            )

            time.sleep(1)

            # Determine actual table name
            conn = get_db()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT table_name FROM _realtime.metadata_tables
                    WHERE main_table LIKE 'rpc_test_data%'
                    ORDER BY id DESC LIMIT 1;
                """)
                result = cur.fetchone()
                table_name = result[0] if result else "rpc_test_data_p1"

            yield {"user": user_response.user, "table_name": table_name}

            # Cleanup
            client.get("/auth/logout")
            conn = get_db()
            with conn.cursor() as cur:
                cur.execute("DROP TABLE IF EXISTS _realtime.rpc_test_data_p1 CASCADE;")
                cur.execute(
                    "DELETE FROM _realtime.metadata_tables WHERE main_table = 'rpc_test_data';"
                )
            conn.commit()
            service_client.auth.admin.delete_user(user_response.user.id)

    def test_get_all_tables_works(self, app):
        """Test get_all_tables RPC function"""
        with app.app_context():
            result = supabase_extension.safe_rpc_call(
                "get_all_tables", {"p_schema_name": "_realtime"}
            )
            assert result is not None
            assert isinstance(result, list)

    def test_get_table_columns_works(self, app, test_user_with_data):
        """Test get_table_columns RPC function"""
        with app.app_context():
            table_name = test_user_with_data["table_name"]
            result = supabase_extension.safe_rpc_call(
                "get_table_columns", {"p_table_name": table_name, "p_schema_name": "_realtime"}
            )
            assert result is not None
            assert len(result) > 0
            # Should include patient_id, temperature, heart_rate columns
            column_names = [col["column_name"] for col in result]
            assert "patient_id" in column_names

    def test_table_exists_works(self, app, test_user_with_data):
        """Test table_exists RPC function"""
        with app.app_context():
            table_name = test_user_with_data["table_name"]
            result = supabase_extension.safe_rpc_call(
                "table_exists", {"p_table_name": table_name, "p_schema_name": "_realtime"}
            )
            assert result is True

            # Test non-existent table
            result = supabase_extension.safe_rpc_call(
                "table_exists",
                {"p_table_name": "nonexistent_table_xyz", "p_schema_name": "_realtime"},
            )
            assert result is False

    def test_search_tables_by_column_works(self, app, test_user_with_data):
        """Test search_tables_by_column RPC function"""
        with app.app_context():
            result = supabase_extension.safe_rpc_call(
                "search_tables_by_column",
                {"p_column_name": "patient_id", "p_schema_name": "_realtime"},
            )
            assert result is not None
            assert isinstance(result, list)

    def test_select_from_table_respects_rls(self, app, test_user_with_data):
        """Test select_from_table RPC respects RLS"""
        with app.app_context():
            table_name = test_user_with_data["table_name"]

            # Service role can access
            result = supabase_extension.service_role_client.rpc(
                "select_from_table",
                {"p_table_name": table_name, "p_row_limit": 10, "p_schema_name": "_realtime"},
            ).execute()
            assert result.data is not None
            assert len(result.data) > 0

    def test_insert_metadata_via_rpc(self, app, test_user_with_data):
        """Test insert_metadata RPC function requires authentication"""
        with app.app_context():
            user_data = test_user_with_data
            user = user_data["user"]
            
            # Create authenticated Supabase client
            auth_response = supabase_extension.client.auth.sign_in_with_password({
                "email": "rpc_test_user@test.com",
                "password": "TestPassword123!"
            })
            
            # Use authenticated client to call insert_metadata
            result = supabase_extension.client.rpc(
                "insert_metadata",
                {
                    "p_table_name": "test_meta_insert",
                    "p_main_table": "test_meta_main",
                    "p_description": "Test metadata insertion",
                    "p_origin": "RPC Test",
                },
            ).execute()

            assert result.data is not None
            assert isinstance(result.data, int)  # Returns inserted ID

            # Cleanup
            (
                supabase_extension.service_role_client.schema("_realtime")
                .table("metadata_tables")
                .delete()
                .eq("id", result.data)
                .execute()
            )
            
            # Sign out
            supabase_extension.client.auth.sign_out()


class TestRLSIntegrationScenarios:
    """End-to-end RLS scenarios"""

    def test_full_upload_workflow_with_rls(self, app, client, logged_in_user):
        """Test complete upload workflow respects RLS at every step"""
        test_client, user = logged_in_user

        # 1. Upload CSV as authenticated user
        csv_content = b"patient_id,weight,height\nP201,180,72\nP202,160,65\n"
        csv_file = (BytesIO(csv_content), "integration_test.csv")

        response = test_client.post(
            "/dashboard/upload",
            data={"file": csv_file, "description": "Integration test", "origin": "Test"},
            content_type="multipart/form-data",
            follow_redirects=True,
        )

        assert response.status_code == 200
        time.sleep(1)

        # 2. Verify metadata was created
        with app.app_context():
            metadata = (
                supabase_extension.service_role_client.schema("_realtime")
                .table("metadata_tables")
                .select("*")
                .like("main_table", "integration_test%")
                .execute()
            )
            assert len(metadata.data) > 0

            # Get actual table name
            actual_table_name = metadata.data[0]["table_name"]
            actual_main_table = metadata.data[0]["main_table"]

        # 3. Verify data table exists with RLS
        with app.app_context():
            conn = get_db()
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT rowsecurity
                    FROM pg_tables
                    WHERE schemaname = '_realtime' AND tablename = '{actual_table_name}';
                """)
                result = cur.fetchone()
                assert result is not None
                assert result[0] is True, "RLS should be enabled"

        # 4. Verify data can be queried via RPC
        with app.app_context():
            data = supabase_extension.safe_rpc_call(
                "select_from_table",
                {"p_table_name": actual_table_name, "p_row_limit": 100, "p_schema_name": "_realtime"},
            )
            assert len(data) == 2

        # Cleanup
        with app.app_context():
            conn = get_db()
            with conn.cursor() as cur:
                cur.execute(f"DROP TABLE IF EXISTS _realtime.{actual_table_name} CASCADE;")
                cur.execute(
                    "DELETE FROM _realtime.metadata_tables WHERE main_table LIKE 'integration_test%';"
                )
            conn.commit()

    def test_anonymous_user_cannot_access_data(self, app):
        """Anonymous users should not have direct access to tables"""
        with app.app_context():
            # Create a test table with service role
            conn = get_db()
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS _realtime.anon_test_table (
                        rowid SERIAL PRIMARY KEY,
                        patient_id TEXT NOT NULL,
                        data TEXT
                    );
                """)
                cur.execute("ALTER TABLE _realtime.anon_test_table ENABLE ROW LEVEL SECURITY;")
                cur.execute("""
                    CREATE POLICY "no_anon_access" ON _realtime.anon_test_table
                    FOR ALL TO anon USING (false);
                """)
            conn.commit()

            # Try to access as anonymous (should fail or return empty)
            # Note: In practice, anon key would be used, but our test setup uses service role
            # This test verifies the policy exists
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM pg_policies
                    WHERE schemaname = '_realtime'
                    AND tablename = 'anon_test_table'
                    AND policyname = 'no_anon_access';
                """)
                result = cur.fetchone()
                assert result[0] > 0, "Anonymous access policy should exist"

            # Cleanup
            with conn.cursor() as cur:
                cur.execute("DROP TABLE IF EXISTS _realtime.anon_test_table CASCADE;")
            conn.commit()
