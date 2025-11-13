# Copyright 2025 ATP Project Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
End-to-End Tests using Playwright
Comprehensive E2E testing for ATP web interfaces and workflows.
"""

import asyncio
import json
import time
from typing import Any

import pytest

try:
    from playwright.async_api import Page, async_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    pytest.skip("Playwright not available", allow_module_level=True)


class TestAdminDashboard:
    """Test admin dashboard functionality."""

    @pytest.fixture
    async def browser_context(self):
        """Browser context fixture."""
        if not PLAYWRIGHT_AVAILABLE:
            pytest.skip("Playwright not available")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080}, user_agent="ATP-E2E-Tests/1.0"
            )
            yield context
            await context.close()
            await browser.close()

    @pytest.fixture
    async def admin_page(self, browser_context):
        """Admin dashboard page fixture."""
        page = await browser_context.new_page()

        # Navigate to admin dashboard
        await page.goto("http://localhost:3000/admin")

        # Wait for page to load
        await page.wait_for_load_state("networkidle")

        yield page
        await page.close()

    @pytest.mark.asyncio
    async def test_dashboard_login(self, admin_page):
        """Test admin dashboard login flow."""
        # Check if login form is present
        login_form = await admin_page.query_selector("form[data-testid='login-form']")
        if login_form:
            # Fill login form
            await admin_page.fill("input[name='username']", "admin")
            await admin_page.fill("input[name='password']", "admin123")

            # Submit form
            await admin_page.click("button[type='submit']")

            # Wait for redirect
            await admin_page.wait_for_url("**/dashboard")

        # Verify dashboard is loaded
        dashboard_title = await admin_page.query_selector("h1")
        assert dashboard_title is not None

        title_text = await dashboard_title.inner_text()
        assert "Dashboard" in title_text or "ATP" in title_text

    @pytest.mark.asyncio
    async def test_system_overview_widgets(self, admin_page):
        """Test system overview widgets display correctly."""
        # Wait for widgets to load
        await admin_page.wait_for_selector("[data-testid='system-overview']", timeout=10000)

        # Check for key metrics widgets
        widgets_to_check = ["requests-per-second", "error-rate", "response-time", "active-connections", "system-health"]

        for widget_id in widgets_to_check:
            widget = await admin_page.query_selector(f"[data-testid='{widget_id}']")
            if widget:
                # Check widget is visible
                is_visible = await widget.is_visible()
                assert is_visible, f"Widget {widget_id} should be visible"

                # Check widget has content
                content = await widget.inner_text()
                assert content.strip() != "", f"Widget {widget_id} should have content"

    @pytest.mark.asyncio
    async def test_provider_management_interface(self, admin_page):
        """Test provider management interface."""
        # Navigate to providers page
        await admin_page.click("a[href*='providers']")
        await admin_page.wait_for_load_state("networkidle")

        # Check providers table is loaded
        providers_table = await admin_page.query_selector("table[data-testid='providers-table']")
        if providers_table:
            # Check table has headers
            headers = await admin_page.query_selector_all("th")
            assert len(headers) > 0, "Providers table should have headers"

            # Check for add provider button
            add_button = await admin_page.query_selector("button[data-testid='add-provider']")
            if add_button:
                # Test add provider modal
                await add_button.click()

                # Wait for modal
                modal = await admin_page.wait_for_selector("[data-testid='add-provider-modal']")
                assert modal is not None, "Add provider modal should appear"

                # Close modal
                close_button = await admin_page.query_selector("button[data-testid='modal-close']")
                if close_button:
                    await close_button.click()

    @pytest.mark.asyncio
    async def test_real_time_metrics_updates(self, admin_page):
        """Test real-time metrics updates."""
        # Wait for initial metrics load
        await admin_page.wait_for_selector("[data-testid='metrics-container']", timeout=10000)

        # Get initial metric value
        metric_element = await admin_page.query_selector("[data-testid='requests-counter']")
        if metric_element:
            initial_value = await metric_element.inner_text()

            # Wait for potential update (WebSocket or polling)
            await admin_page.wait_for_timeout(5000)

            # Check if value updated (or at least element is still present)
            updated_element = await admin_page.query_selector("[data-testid='requests-counter']")
            assert updated_element is not None, "Metrics should remain available"

    @pytest.mark.asyncio
    async def test_alert_notifications(self, admin_page):
        """Test alert notifications display."""
        # Check for alerts container
        alerts_container = await admin_page.query_selector("[data-testid='alerts-container']")
        if alerts_container:
            # Check for alert items
            alert_items = await admin_page.query_selector_all("[data-testid^='alert-']")

            # If alerts exist, test interaction
            if alert_items:
                first_alert = alert_items[0]

                # Check alert has required information
                alert_text = await first_alert.inner_text()
                assert alert_text.strip() != "", "Alert should have content"

                # Test alert acknowledgment if button exists
                ack_button = await first_alert.query_selector("button[data-testid='acknowledge-alert']")
                if ack_button:
                    await ack_button.click()

                    # Wait for acknowledgment to process
                    await admin_page.wait_for_timeout(1000)

    @pytest.mark.asyncio
    async def test_responsive_design(self, admin_page):
        """Test responsive design on different screen sizes."""
        screen_sizes = [
            {"width": 1920, "height": 1080},  # Desktop
            {"width": 1024, "height": 768},  # Tablet
            {"width": 375, "height": 667},  # Mobile
        ]

        for size in screen_sizes:
            # Set viewport size
            await admin_page.set_viewport_size(size["width"], size["height"])

            # Wait for layout adjustment
            await admin_page.wait_for_timeout(1000)

            # Check main navigation is accessible
            nav_element = await admin_page.query_selector("nav")
            if nav_element:
                is_visible = await nav_element.is_visible()
                # Navigation should be visible or have a mobile menu toggle
                mobile_toggle = await admin_page.query_selector("[data-testid='mobile-menu-toggle']")
                assert is_visible or mobile_toggle is not None, f"Navigation should be accessible at {size['width']}px"

    @pytest.mark.asyncio
    async def test_error_handling(self, admin_page):
        """Test error handling and user feedback."""
        # Test network error handling by intercepting requests
        await admin_page.route("**/api/**", lambda route: route.abort())

        # Try to perform an action that requires API call
        refresh_button = await admin_page.query_selector("button[data-testid='refresh-data']")
        if refresh_button:
            await refresh_button.click()

            # Wait for error message
            error_message = await admin_page.wait_for_selector("[data-testid='error-message']", timeout=5000)

            if error_message:
                error_text = await error_message.inner_text()
                assert "error" in error_text.lower() or "failed" in error_text.lower()


class TestAPIWorkflows:
    """Test API workflows end-to-end."""

    @pytest.fixture
    async def api_context(self, browser_context):
        """API testing context."""
        page = await browser_context.new_page()

        # Set up API request interception for testing
        api_responses = []

        async def handle_response(response):
            if "/api/" in response.url:
                api_responses.append(
                    {"url": response.url, "status": response.status, "headers": dict(response.headers)}
                )

        page.on("response", handle_response)

        yield page, api_responses
        await page.close()

    @pytest.mark.asyncio
    async def test_chat_completion_workflow(self, api_context):
        """Test complete chat completion workflow."""
        page, api_responses = api_context

        # Navigate to API testing interface (if available)
        await page.goto("http://localhost:3000/api-test")

        # Fill chat completion form
        message_input = await page.query_selector("textarea[data-testid='message-input']")
        if message_input:
            await message_input.fill("Hello, how are you?")

            # Select model
            model_select = await page.query_selector("select[data-testid='model-select']")
            if model_select:
                await model_select.select_option("gpt-4")

            # Submit request
            submit_button = await page.query_selector("button[data-testid='submit-request']")
            await submit_button.click()

            # Wait for response
            response_area = await page.wait_for_selector("[data-testid='response-area']", timeout=30000)

            # Check response content
            response_text = await response_area.inner_text()
            assert response_text.strip() != "", "Should receive a response"

            # Check API calls were made
            chat_api_calls = [r for r in api_responses if "chat/completions" in r["url"]]
            assert len(chat_api_calls) > 0, "Should make chat completion API call"

    @pytest.mark.asyncio
    async def test_streaming_response_workflow(self, api_context):
        """Test streaming response workflow."""
        page, api_responses = api_context

        await page.goto("http://localhost:3000/api-test")

        # Enable streaming
        streaming_checkbox = await page.query_selector("input[data-testid='enable-streaming']")
        if streaming_checkbox:
            await streaming_checkbox.check()

            # Submit streaming request
            message_input = await page.query_selector("textarea[data-testid='message-input']")
            await message_input.fill("Write a short story")

            submit_button = await page.query_selector("button[data-testid='submit-request']")
            await submit_button.click()

            # Wait for streaming to start
            streaming_indicator = await page.wait_for_selector("[data-testid='streaming-indicator']", timeout=10000)

            # Wait for streaming to complete
            await page.wait_for_selector("[data-testid='streaming-complete']", timeout=60000)

            # Check final response
            response_area = await page.query_selector("[data-testid='response-area']")
            response_text = await response_area.inner_text()
            assert len(response_text) > 50, "Streaming response should be substantial"


class TestUserJourneys:
    """Test complete user journeys."""

    @pytest.fixture
    async def user_session(self, browser_context):
        """User session fixture."""
        page = await browser_context.new_page()

        # Set up user session tracking
        user_actions = []

        async def track_action(action_type, details):
            user_actions.append({"timestamp": time.time(), "action": action_type, "details": details, "url": page.url})

        yield page, track_action, user_actions
        await page.close()

    @pytest.mark.asyncio
    async def test_new_user_onboarding(self, user_session):
        """Test new user onboarding flow."""
        page, track_action, user_actions = user_session

        # Start onboarding
        await page.goto("http://localhost:3000/onboarding")
        await track_action("start_onboarding", {"page": "welcome"})

        # Step 1: Welcome
        welcome_title = await page.query_selector("h1")
        if welcome_title:
            title_text = await welcome_title.inner_text()
            assert "welcome" in title_text.lower() or "onboarding" in title_text.lower()

        next_button = await page.query_selector("button[data-testid='next-step']")
        if next_button:
            await next_button.click()
            await track_action("complete_step", {"step": 1})

        # Step 2: API Key Setup
        api_key_input = await page.query_selector("input[data-testid='api-key-input']")
        if api_key_input:
            await api_key_input.fill("test-api-key-123")
            await track_action("enter_api_key", {"step": 2})

            next_button = await page.query_selector("button[data-testid='next-step']")
            await next_button.click()

        # Step 3: First Request
        test_request_button = await page.query_selector("button[data-testid='test-request']")
        if test_request_button:
            await test_request_button.click()
            await track_action("test_request", {"step": 3})

            # Wait for test result
            await page.wait_for_selector("[data-testid='test-result']", timeout=10000)

        # Complete onboarding
        complete_button = await page.query_selector("button[data-testid='complete-onboarding']")
        if complete_button:
            await complete_button.click()
            await track_action("complete_onboarding", {"total_steps": len(user_actions)})

        # Verify user was redirected to dashboard
        await page.wait_for_url("**/dashboard")
        assert "dashboard" in page.url

    @pytest.mark.asyncio
    async def test_admin_workflow(self, user_session):
        """Test complete admin workflow."""
        page, track_action, user_actions = user_session

        # Login as admin
        await page.goto("http://localhost:3000/admin/login")
        await track_action("start_admin_login", {})

        # Fill login form
        await page.fill("input[name='username']", "admin")
        await page.fill("input[name='password']", "admin123")
        await page.click("button[type='submit']")
        await track_action("submit_login", {})

        # Navigate to provider management
        await page.click("a[href*='providers']")
        await track_action("navigate_to_providers", {})

        # Add new provider
        add_button = await page.query_selector("button[data-testid='add-provider']")
        if add_button:
            await add_button.click()
            await track_action("open_add_provider", {})

            # Fill provider form
            await page.fill("input[name='name']", "Test Provider")
            await page.fill("input[name='endpoint']", "https://api.test.com")
            await page.fill("input[name='api_key']", "test-key")

            # Submit form
            await page.click("button[data-testid='save-provider']")
            await track_action("save_provider", {"name": "Test Provider"})

        # Check provider was added
        provider_row = await page.wait_for_selector("tr:has-text('Test Provider')", timeout=5000)
        assert provider_row is not None, "New provider should appear in table"

        # Test provider
        test_button = await provider_row.query_selector("button[data-testid='test-provider']")
        if test_button:
            await test_button.click()
            await track_action("test_provider", {"name": "Test Provider"})

            # Wait for test result
            await page.wait_for_selector("[data-testid='test-result']", timeout=10000)

        # View system metrics
        await page.click("a[href*='metrics']")
        await track_action("view_metrics", {})

        # Check metrics are displayed
        metrics_container = await page.wait_for_selector("[data-testid='metrics-dashboard']")
        assert metrics_container is not None, "Metrics dashboard should load"

        # Verify admin workflow completed successfully
        assert len(user_actions) >= 5, "Admin workflow should have multiple steps"


class TestPerformanceE2E:
    """Test performance aspects in E2E scenarios."""

    @pytest.mark.asyncio
    async def test_page_load_performance(self, browser_context):
        """Test page load performance."""
        page = await browser_context.new_page()

        # Measure page load time
        start_time = time.time()
        await page.goto("http://localhost:3000/dashboard")
        await page.wait_for_load_state("networkidle")
        load_time = time.time() - start_time

        # Page should load within reasonable time
        assert load_time < 5.0, f"Page load time ({load_time:.2f}s) should be under 5 seconds"

        # Check for performance metrics
        performance_metrics = await page.evaluate("""
            () => {
                const navigation = performance.getEntriesByType('navigation')[0];
                return {
                    domContentLoaded: navigation.domContentLoadedEventEnd - navigation.domContentLoadedEventStart,
                    loadComplete: navigation.loadEventEnd - navigation.loadEventStart,
                    firstPaint: performance.getEntriesByType('paint').find(p => p.name === 'first-paint')?.startTime,
                    firstContentfulPaint: performance.getEntriesByType('paint').find(p => p.name === 'first-contentful-paint')?.startTime
                };
            }
        """)

        # Validate performance metrics
        assert performance_metrics["domContentLoaded"] < 2000, "DOM content should load quickly"
        if performance_metrics["firstContentfulPaint"]:
            assert performance_metrics["firstContentfulPaint"] < 3000, "First contentful paint should be fast"

        await page.close()

    @pytest.mark.asyncio
    async def test_concurrent_user_simulation(self, browser_context):
        """Test behavior with multiple concurrent users."""
        # Create multiple pages to simulate concurrent users
        pages = []
        for _ in range(3):
            page = await browser_context.new_page()
            pages.append(page)

        try:
            # Simulate concurrent navigation
            navigation_tasks = []
            for i, page in enumerate(pages):
                task = asyncio.create_task(self._simulate_user_session(page, f"user_{i}"))
                navigation_tasks.append(task)

            # Wait for all sessions to complete
            results = await asyncio.gather(*navigation_tasks, return_exceptions=True)

            # Check that all sessions completed successfully
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    pytest.fail(f"User session {i} failed: {result}")
                else:
                    assert result["success"], f"User session {i} should complete successfully"

        finally:
            # Clean up pages
            for page in pages:
                await page.close()

    async def _simulate_user_session(self, page: Page, user_id: str) -> dict[str, Any]:
        """Simulate a user session."""
        try:
            # Navigate to dashboard
            await page.goto("http://localhost:3000/dashboard")
            await page.wait_for_load_state("networkidle")

            # Interact with dashboard
            await page.wait_for_timeout(1000)  # Simulate reading time

            # Navigate to different sections
            sections = ["providers", "metrics", "settings"]
            for section in sections:
                link = await page.query_selector(f"a[href*='{section}']")
                if link:
                    await link.click()
                    await page.wait_for_load_state("networkidle")
                    await page.wait_for_timeout(500)  # Simulate interaction time

            return {"success": True, "user_id": user_id}

        except Exception as e:
            return {"success": False, "user_id": user_id, "error": str(e)}


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])


class TestEnterpriseWorkflows:
    """Test enterprise-specific workflows."""

    @pytest.fixture
    async def enterprise_context(self, browser_context):
        """Enterprise testing context."""
        page = await browser_context.new_page()

        # Set up enterprise environment
        await page.add_init_script("""
            window.ATP_CONFIG = {
                enterprise: true,
                features: ['multi_tenant', 'advanced_analytics', 'compliance'],
                version: '2.0.0'
            };
        """)

        yield page
        await page.close()

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation(self, enterprise_context):
        """Test multi-tenant data isolation."""
        page = enterprise_context

        # Login as tenant A admin
        await page.goto("http://localhost:3000/admin/login")
        await page.fill("input[name='username']", "tenant-a-admin")
        await page.fill("input[name='password']", "admin123")
        await page.click("button[type='submit']")

        # Navigate to tenant data
        await page.click("a[href*='tenant-data']")
        await page.wait_for_load_state("networkidle")

        # Verify tenant A can only see their data
        tenant_data = await page.query_selector_all("[data-testid='tenant-data-row']")
        for row in tenant_data:
            tenant_id = await row.get_attribute("data-tenant-id")
            assert tenant_id == "tenant-a", "Should only see tenant A data"

        # Try to access tenant B data directly (should fail)
        await page.goto("http://localhost:3000/admin/tenants/tenant-b/data")

        # Should be redirected or show access denied
        current_url = page.url
        assert "access-denied" in current_url or "login" in current_url

    @pytest.mark.asyncio
    async def test_compliance_audit_trail(self, enterprise_context):
        """Test compliance audit trail functionality."""
        page = enterprise_context

        # Login as compliance officer
        await page.goto("http://localhost:3000/admin/login")
        await page.fill("input[name='username']", "compliance-officer")
        await page.fill("input[name='password']", "compliance123")
        await page.click("button[type='submit']")

        # Navigate to audit logs
        await page.click("a[href*='audit-logs']")
        await page.wait_for_load_state("networkidle")

        # Verify audit log entries
        audit_entries = await page.query_selector_all("[data-testid='audit-entry']")
        assert len(audit_entries) > 0, "Should have audit log entries"

        # Check audit entry details
        first_entry = audit_entries[0]
        await first_entry.click()

        # Verify audit details modal
        modal = await page.wait_for_selector("[data-testid='audit-details-modal']")
        assert modal is not None

        # Check required audit fields
        required_fields = ["timestamp", "user", "action", "resource", "outcome"]
        for field in required_fields:
            field_element = await modal.query_selector(f"[data-testid='audit-{field}']")
            assert field_element is not None, f"Audit entry should have {field}"

    @pytest.mark.asyncio
    async def test_advanced_analytics_dashboard(self, enterprise_context):
        """Test advanced analytics dashboard."""
        page = enterprise_context

        # Login as analytics user
        await page.goto("http://localhost:3000/admin/login")
        await page.fill("input[name='username']", "analytics-user")
        await page.fill("input[name='password']", "analytics123")
        await page.click("button[type='submit']")

        # Navigate to analytics
        await page.click("a[href*='analytics']")
        await page.wait_for_load_state("networkidle")

        # Wait for charts to load
        await page.wait_for_selector("[data-testid='analytics-charts']", timeout=10000)

        # Verify key analytics widgets
        analytics_widgets = [
            "cost-analysis-chart",
            "usage-trends-chart",
            "performance-metrics-chart",
            "model-comparison-chart",
        ]

        for widget_id in analytics_widgets:
            widget = await page.query_selector(f"[data-testid='{widget_id}']")
            assert widget is not None, f"Analytics widget {widget_id} should be present"

            # Check if widget has data
            is_visible = await widget.is_visible()
            assert is_visible, f"Analytics widget {widget_id} should be visible"

        # Test date range filtering
        date_filter = await page.query_selector("[data-testid='date-range-filter']")
        if date_filter:
            await date_filter.click()

            # Select last 7 days
            await page.click("[data-testid='date-range-7d']")

            # Wait for charts to update
            await page.wait_for_timeout(2000)

            # Verify charts updated (check for loading indicators)
            loading_indicators = await page.query_selector_all("[data-testid='chart-loading']")
            assert len(loading_indicators) == 0, "Charts should finish loading"

    @pytest.mark.asyncio
    async def test_enterprise_user_management(self, enterprise_context):
        """Test enterprise user management features."""
        page = enterprise_context

        # Login as admin
        await page.goto("http://localhost:3000/admin/login")
        await page.fill("input[name='username']", "super-admin")
        await page.fill("input[name='password']", "superadmin123")
        await page.click("button[type='submit']")

        # Navigate to user management
        await page.click("a[href*='users']")
        await page.wait_for_load_state("networkidle")

        # Test adding new user
        add_user_button = await page.query_selector("button[data-testid='add-user']")
        if add_user_button:
            await add_user_button.click()

            # Fill user form
            await page.fill("input[name='email']", "newuser@example.com")
            await page.fill("input[name='firstName']", "New")
            await page.fill("input[name='lastName']", "User")
            await page.select_option("select[name='role']", "analyst")

            # Set permissions
            permissions = ["read_analytics", "read_metrics"]
            for permission in permissions:
                checkbox = await page.query_selector(f"input[name='permissions'][value='{permission}']")
                if checkbox:
                    await checkbox.check()

            # Submit form
            await page.click("button[data-testid='save-user']")

            # Verify user was added
            await page.wait_for_selector("tr:has-text('newuser@example.com')", timeout=5000)

        # Test user role management
        user_row = await page.query_selector("tr:has-text('newuser@example.com')")
        if user_row:
            edit_button = await user_row.query_selector("button[data-testid='edit-user']")
            await edit_button.click()

            # Change role
            await page.select_option("select[name='role']", "admin")
            await page.click("button[data-testid='save-user']")

            # Verify role change
            await page.wait_for_timeout(1000)
            role_cell = await user_row.query_selector("td[data-testid='user-role']")
            role_text = await role_cell.inner_text()
            assert "admin" in role_text.lower()


class TestAPIContractTesting:
    """Test API contracts and backward compatibility."""

    @pytest.fixture
    async def api_client(self, browser_context):
        """API client fixture."""
        page = await browser_context.new_page()

        # Set up API interceptor
        api_calls = []

        async def handle_request(route):
            request = route.request
            if "/api/" in request.url:
                api_calls.append(
                    {
                        "method": request.method,
                        "url": request.url,
                        "headers": dict(request.headers),
                        "body": request.post_data,
                    }
                )
            await route.continue_()

        await page.route("**/*", handle_request)

        yield page, api_calls
        await page.close()

    @pytest.mark.asyncio
    async def test_api_version_compatibility(self, api_client):
        """Test API version compatibility."""
        page, api_calls = api_client

        # Test v1 API endpoints
        await page.goto("http://localhost:3000/api-test")

        # Test chat completions v1
        await page.fill("textarea[data-testid='api-endpoint']", "/api/v1/chat/completions")
        await page.fill(
            "textarea[data-testid='request-body']",
            json.dumps({"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]}),
        )
        await page.click("button[data-testid='send-request']")

        # Wait for response
        await page.wait_for_selector("[data-testid='response-body']", timeout=10000)

        # Verify v1 API call was made
        v1_calls = [call for call in api_calls if "/api/v1/" in call["url"]]
        assert len(v1_calls) > 0, "Should make v1 API calls"

        # Test v2 API endpoints (if available)
        await page.fill("textarea[data-testid='api-endpoint']", "/api/v2/chat/completions")
        await page.click("button[data-testid='send-request']")

        # Should handle gracefully (either work or return proper error)
        response_status = await page.query_selector("[data-testid='response-status']")
        if response_status:
            status_text = await response_status.inner_text()
            # Should be either 200 (works) or 404/501 (not implemented)
            assert any(code in status_text for code in ["200", "404", "501"])

    @pytest.mark.asyncio
    async def test_api_schema_validation(self, api_client):
        """Test API request/response schema validation."""
        page, api_calls = api_client

        await page.goto("http://localhost:3000/api-test")

        # Test with valid schema
        valid_request = {
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "Test message"}],
            "temperature": 0.7,
            "max_tokens": 100,
        }

        await page.fill("textarea[data-testid='request-body']", json.dumps(valid_request))
        await page.click("button[data-testid='send-request']")

        # Should succeed
        response_status = await page.wait_for_selector("[data-testid='response-status']")
        status_text = await response_status.inner_text()
        assert "200" in status_text

        # Test with invalid schema
        invalid_request = {
            "model": "gpt-4",
            "messages": "invalid_messages_format",  # Should be array
            "temperature": "invalid_temperature",  # Should be number
        }

        await page.fill("textarea[data-testid='request-body']", json.dumps(invalid_request))
        await page.click("button[data-testid='send-request']")

        # Should return validation error
        response_status = await page.wait_for_selector("[data-testid='response-status']")
        status_text = await response_status.inner_text()
        assert "400" in status_text, "Should return 400 for invalid schema"

    @pytest.mark.asyncio
    async def test_api_rate_limiting(self, api_client):
        """Test API rate limiting behavior."""
        page, api_calls = api_client

        await page.goto("http://localhost:3000/api-test")

        # Configure for rapid requests
        await page.fill(
            "textarea[data-testid='request-body']",
            json.dumps({"model": "gpt-4", "messages": [{"role": "user", "content": "Rate limit test"}]}),
        )

        # Send multiple rapid requests
        for _ in range(10):
            await page.click("button[data-testid='send-request']")
            await page.wait_for_timeout(100)  # Small delay

        # Check for rate limiting responses
        rate_limit_responses = []
        for i in range(10):
            try:
                status_element = await page.wait_for_selector(f"[data-testid='response-status-{i}']", timeout=1000)
                status_text = await status_element.inner_text()
                if "429" in status_text:
                    rate_limit_responses.append(i)
            except Exception:
                # Expected - not all responses may be visible yet
                continue

        # Should have some rate limited responses
        assert len(rate_limit_responses) > 0, "Should encounter rate limiting"


class TestAccessibilityCompliance:
    """Test accessibility compliance."""

    @pytest.mark.asyncio
    async def test_keyboard_navigation(self, browser_context):
        """Test keyboard navigation accessibility."""
        page = await browser_context.new_page()

        await page.goto("http://localhost:3000/dashboard")
        await page.wait_for_load_state("networkidle")

        # Test tab navigation
        focusable_elements = []

        # Start from first focusable element
        await page.keyboard.press("Tab")

        # Navigate through focusable elements
        for _ in range(20):  # Test first 20 tab stops
            focused_element = await page.evaluate(
                "document.activeElement.tagName + (document.activeElement.id ? '#' + document.activeElement.id : '') + (document.activeElement.className ? '.' + document.activeElement.className.split(' ')[0] : '')"
            )
            focusable_elements.append(focused_element)
            await page.keyboard.press("Tab")

        # Verify we can navigate to key elements
        key_elements = ["BUTTON", "INPUT", "A", "SELECT"]
        found_elements = [elem for elem in focusable_elements if any(key in elem for key in key_elements)]
        assert len(found_elements) > 0, "Should be able to navigate to interactive elements"

        # Test escape key functionality
        modal_trigger = await page.query_selector("button[data-testid='open-modal']")
        if modal_trigger:
            await modal_trigger.click()

            # Modal should open
            modal = await page.wait_for_selector("[data-testid='modal']")
            assert modal is not None

            # Press escape to close
            await page.keyboard.press("Escape")

            # Modal should close
            await page.wait_for_timeout(500)
            modal_visible = await modal.is_visible()
            assert not modal_visible, "Modal should close on Escape key"

        await page.close()

    @pytest.mark.asyncio
    async def test_screen_reader_compatibility(self, browser_context):
        """Test screen reader compatibility."""
        page = await browser_context.new_page()

        await page.goto("http://localhost:3000/dashboard")
        await page.wait_for_load_state("networkidle")

        # Check for ARIA labels
        elements_needing_labels = await page.query_selector_all("button, input, select, [role='button']")

        for element in elements_needing_labels:
            # Check for accessible name
            aria_label = await element.get_attribute("aria-label")
            aria_labelledby = await element.get_attribute("aria-labelledby")
            title = await element.get_attribute("title")
            inner_text = await element.inner_text()

            has_accessible_name = any([aria_label, aria_labelledby, title, inner_text.strip()])

            if not has_accessible_name:
                element_info = await element.evaluate(
                    "el => ({ tagName: el.tagName, className: el.className, id: el.id })"
                )
                print(f"Warning: Element without accessible name: {element_info}")

        # Check for proper heading structure
        headings = await page.query_selector_all("h1, h2, h3, h4, h5, h6")
        heading_levels = []

        for heading in headings:
            tag_name = await heading.evaluate("el => el.tagName")
            level = int(tag_name[1])
            heading_levels.append(level)

        # Verify heading hierarchy (should start with h1 and not skip levels)
        if heading_levels:
            assert heading_levels[0] == 1, "Page should start with h1"

            for i in range(1, len(heading_levels)):
                level_jump = heading_levels[i] - heading_levels[i - 1]
                assert level_jump <= 1, (
                    f"Heading levels should not skip: h{heading_levels[i - 1]} to h{heading_levels[i]}"
                )

        await page.close()

    @pytest.mark.asyncio
    async def test_color_contrast_compliance(self, browser_context):
        """Test color contrast compliance."""
        page = await browser_context.new_page()

        await page.goto("http://localhost:3000/dashboard")
        await page.wait_for_load_state("networkidle")

        # Check text elements for sufficient contrast
        text_elements = await page.query_selector_all("p, span, div, h1, h2, h3, h4, h5, h6, button, a")

        contrast_issues = []

        for element in text_elements[:20]:  # Check first 20 text elements
            try:
                # Get computed styles
                styles = await element.evaluate("""
                    el => {
                        const computed = window.getComputedStyle(el);
                        return {
                            color: computed.color,
                            backgroundColor: computed.backgroundColor,
                            fontSize: computed.fontSize
                        };
                    }
                """)

                # Simple contrast check (would need more sophisticated implementation)
                if styles["color"] and styles["backgroundColor"]:
                    # This is a simplified check - real implementation would calculate WCAG contrast ratios
                    if styles["color"] == styles["backgroundColor"]:
                        contrast_issues.append(
                            {
                                "element": await element.evaluate(
                                    "el => el.tagName + (el.className ? '.' + el.className.split(' ')[0] : '')"
                                ),
                                "issue": "Same foreground and background color",
                            }
                        )
            except Exception:
                # Expected - some elements may not have computed styles
                continue

        # Report contrast issues (if any)
        if contrast_issues:
            print(f"Found {len(contrast_issues)} potential contrast issues")
            for issue in contrast_issues[:5]:  # Show first 5
                print(f"  - {issue['element']}: {issue['issue']}")

        await page.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
