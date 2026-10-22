"""
test_loader.py — Tests for leads.csv loading and validation.
"""

import csv
import os
import pytest
import tempfile

# We need to patch the constants in agent.py for testing
import agent


@pytest.fixture
def tmp_leads(tmp_path):
    """Helper to create a temporary leads.csv and point agent.py at it."""
    def _write(rows, header=None):
        if header is None:
            header = "company,website,person_name,person_role,email,linkedin,category,goal,hook_notes,extra_urls,event_name,event_phase"
        filepath = tmp_path / "leads.csv"
        filepath.write_text(header + "\n" + "\n".join(rows), encoding="utf-8")
        # Patch the module-level constant
        agent.LEADS_FILE = str(filepath)
        return filepath
    return _write


class TestLeadsLoader:
    def test_valid_rows_load(self, tmp_leads):
        tmp_leads([
            'Acme,https://acme.ai,Jane Roe,CTO,jane@acme.ai,,openings,"AI intern","hook",,,'
        ])
        leads = agent.load_leads()
        assert len(leads) == 1
        assert leads[0]["company"] == "Acme"

    def test_missing_required_column_skipped(self, tmp_leads):
        tmp_leads([
            # Missing 'goal' value
            'Acme,https://acme.ai,Jane Roe,CTO,jane@acme.ai,,openings,,"hook",,,'
        ])
        leads = agent.load_leads()
        assert len(leads) == 0

    def test_unknown_category_skipped(self, tmp_leads):
        tmp_leads([
            'Acme,https://acme.ai,Jane Roe,CTO,jane@acme.ai,,unknown_cat,"AI intern","hook",,,'
        ])
        leads = agent.load_leads()
        assert len(leads) == 0

    def test_duplicate_rows_deduped(self, tmp_leads):
        tmp_leads([
            'Acme,https://acme.ai,Jane Roe,CTO,jane@acme.ai,,openings,"AI intern","hook",,,',
            'Acme,https://acme.ai,Jane Roe,CTO,jane@acme.ai,,openings,"AI intern","hook2",,,',
        ])
        leads = agent.load_leads()
        assert len(leads) == 1

    def test_blank_email_loads(self, tmp_leads):
        """Leads with blank email should still load (they go to needs_manual)."""
        tmp_leads([
            'Acme,https://acme.ai,Jane Roe,CTO,,https://linkedin.com/jane,connect,"connect","hook",,,'
        ])
        leads = agent.load_leads()
        assert len(leads) == 1
        assert leads[0]["email"] == ""

    def test_whitespace_trimmed(self, tmp_leads):
        tmp_leads([
            '  Acme  , https://acme.ai , Jane Roe ,CTO,jane@acme.ai,,openings, AI intern ,hook,,,'
        ])
        leads = agent.load_leads()
        assert len(leads) == 1
        assert leads[0]["company"] == "Acme"
        assert leads[0]["website"] == "https://acme.ai"
