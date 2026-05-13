"""
Playwright tests for the Claude Token Usage Dashboard.
Starts Flask on port 5050 before tests, tears it down after.
"""
import subprocess
import sys
import time
import os
import pytest
import requests
from playwright.sync_api import Page, sync_playwright


FLASK_PORT = 5050
BASE_URL = f"http://localhost:{FLASK_PORT}"
APP_DIR = os.path.join(os.path.dirname(__file__), "..")


def wait_for_server(url: str, timeout: int = 15) -> bool:
    """Poll until the server responds or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(url, timeout=2)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


@pytest.fixture(scope="session")
def flask_server():
    """Start the Flask app as a subprocess and yield; then kill it."""
    proc = subprocess.Popen(
        [sys.executable, "app.py"],
        cwd=APP_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    ready = wait_for_server(BASE_URL)
    if not ready:
        proc.kill()
        stdout, stderr = proc.communicate()
        raise RuntimeError(
            f"Flask server did not start in time.\n"
            f"STDOUT: {stdout.decode()}\nSTDERR: {stderr.decode()}"
        )
    yield proc
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="session")
def browser_page(flask_server):
    """Single shared browser page for all tests."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(BASE_URL, wait_until="networkidle")
        yield page
        browser.close()


# ── Test 1: Page loads and title is visible ──────────────────────────────────

def test_page_title_visible(browser_page: Page):
    """Dashboard title should be visible on the page."""
    title_el = browser_page.locator("h1")
    assert title_el.count() >= 1, "No <h1> found on page"
    title_text = title_el.first.inner_text()
    assert "claude" in title_text.lower() or "token" in title_text.lower() or "usage" in title_text.lower(), (
        f"Title doesn't look like a dashboard header: {title_text!r}"
    )


# ── Test 2: Summary table has at least one data row ──────────────────────────

def test_table_has_data_rows(browser_page: Page):
    """The summary table body should have at least one row."""
    # Wait for JS to populate the table
    browser_page.wait_for_selector("#tableBody tr", timeout=10_000)
    rows = browser_page.locator("#tableBody tr")
    count = rows.count()
    assert count >= 1, f"Expected ≥1 table rows, got {count}"


# ── Test 3: Model filter dropdown has at least one model option ───────────────

def test_model_filter_has_options(browser_page: Page):
    """The model multi-select should contain at least one real model option."""
    sel = browser_page.locator("#modelFilter")
    # Options: "All Models" + actual models
    options = sel.locator("option")
    count = options.count()
    assert count >= 2, f"Expected ≥2 options in model filter (All Models + ≥1 model), got {count}"
    # Verify "All Models" option is present
    all_models_opt = sel.locator("option[value='__all__']")
    assert all_models_opt.count() == 1, "Missing 'All Models' option"


# ── Test 4: Selecting a specific model filters the table ──────────────────────

def test_model_filter_filters_table(browser_page: Page):
    """Selecting a specific model should result in ≥1 row in the filtered table."""
    sel = browser_page.locator("#modelFilter")
    options = sel.locator("option")

    # Get the second option (first real model after "All Models")
    second_option_value = options.nth(1).get_attribute("value")

    # Select just that model via JS (to avoid multi-select complexity)
    browser_page.evaluate(f"""
        const sel = document.getElementById('modelFilter');
        for (const opt of sel.options) {{
            opt.selected = opt.value === '{second_option_value}';
        }}
        sel.dispatchEvent(new Event('change'));
    """)

    # Wait briefly for re-render
    browser_page.wait_for_timeout(500)

    rows = browser_page.locator("#tableBody tr")
    count = rows.count()
    assert count >= 1, f"After filtering by model '{second_option_value}', got {count} rows (expected ≥1)"

    # Reset filters for subsequent tests
    browser_page.evaluate("""
        const sel = document.getElementById('modelFilter');
        for (const opt of sel.options) {
            opt.selected = opt.value === '__all__';
        }
        sel.dispatchEvent(new Event('change'));
    """)
    browser_page.wait_for_timeout(500)


# ── Test 5: Totals row exists and shows non-zero tokens ───────────────────────

def test_totals_row_nonzero(browser_page: Page):
    """The TOTALS footer row should exist and show non-zero token counts."""
    totals_row = browser_page.locator("#totalsRow")
    assert totals_row.count() == 1, "TOTALS row not found in table footer"

    # Check total cell (last cell in totals row)
    total_cell = browser_page.locator("#totTotal")
    assert total_cell.count() == 1, "Total cell (#totTotal) not found"

    total_text = total_cell.inner_text().strip().replace(",", "")
    assert total_text.isdigit() and int(total_text) > 0, (
        f"Expected non-zero total in TOTALS row, got: {total_text!r}"
    )
