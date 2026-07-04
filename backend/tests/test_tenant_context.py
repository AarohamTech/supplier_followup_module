"""Tests for the tenant context module."""
import unittest
from app.core.tenant import (
    DEFAULT_SCHEMA,
    get_current_schema,
    set_current_schema,
    reset_current_schema,
    use_company,
)


class TestTenantContext(unittest.TestCase):
    """Test suite for per-request tenant context."""

    def test_default_schema_constant(self):
        """DEFAULT_SCHEMA should be 'public'."""
        self.assertEqual(DEFAULT_SCHEMA, "public")

    def test_get_current_schema_default(self):
        """get_current_schema() should return 'public' by default."""
        self.assertEqual(get_current_schema(), "public")

    def test_use_company_context_manager(self):
        """Inside use_company('company_101'), schema should change; after it should revert."""
        # Before
        self.assertEqual(get_current_schema(), "public")

        # Inside
        with use_company("company_101"):
            self.assertEqual(get_current_schema(), "company_101")

        # After
        self.assertEqual(get_current_schema(), "public")

    def test_nested_use_company(self):
        """Nested use_company contexts should restore correctly."""
        # Outer context
        with use_company("company_101"):
            self.assertEqual(get_current_schema(), "company_101")

            # Inner context
            with use_company("company_202"):
                self.assertEqual(get_current_schema(), "company_202")

            # After inner context
            self.assertEqual(get_current_schema(), "company_101")

        # After outer context
        self.assertEqual(get_current_schema(), "public")

    def test_use_company_with_none_and_empty_string(self):
        """use_company(None) and use_company('') should resolve to 'public'."""
        # Test with None
        with use_company(None):
            self.assertEqual(get_current_schema(), "public")

        # Test with empty string
        with use_company(""):
            self.assertEqual(get_current_schema(), "public")

    def test_set_and_reset_current_schema(self):
        """set_current_schema() should return a token that can reset the schema."""
        # Initial state
        self.assertEqual(get_current_schema(), "public")

        # Set to company_101
        token = set_current_schema("company_101")
        self.assertEqual(get_current_schema(), "company_101")

        # Reset using token
        reset_current_schema(token)
        self.assertEqual(get_current_schema(), "public")


if __name__ == "__main__":
    unittest.main()
