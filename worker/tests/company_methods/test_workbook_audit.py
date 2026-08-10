from __future__ import annotations

from pathlib import Path

from worker.tools.audit_company_workbook import audit


def test_workbook_audit_when_source_file_is_available():
    workbook = Path("C:/Users/Maksy/Desktop/testy.xlsx")
    if not workbook.exists():
        return
    result = audit(workbook, Path("method-specs"))
    assert result["passed"] is True
