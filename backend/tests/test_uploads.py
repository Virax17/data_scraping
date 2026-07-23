"""_parse_rows column detection, including the optional region columns."""

import io

import openpyxl

from app.api.uploads import _parse_rows


def _xlsx_bytes(rows: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_rows_without_region_columns_backward_compatible():
    content = _xlsx_bytes([
        ["Company Name", "Website"],
        ["Acme Refinery", "acme.com"],
    ])
    rows = _parse_rows("in.xlsx", content)
    assert rows == [{"name": "Acme Refinery", "website": "acme.com",
                     "country": None, "city": None}]


def test_parse_rows_with_region_columns():
    content = _xlsx_bytes([
        ["Company Name", "Website", "Country", "City"],
        ["Acme Refinery", "acme.com", "United States", "Houston"],
        ["Globex", "globex.com", "", ""],
    ])
    rows = _parse_rows("in.xlsx", content)
    assert rows[0]["country"] == "United States"
    assert rows[0]["city"] == "Houston"
    assert rows[1]["country"] is None
    assert rows[1]["city"] is None


def test_parse_rows_region_alias_and_csv():
    content = b"Company Name,Website,Region,City\nAcme,acme.com,France,Paris\n"
    rows = _parse_rows("in.csv", content)
    assert rows == [{"name": "Acme", "website": "acme.com",
                     "country": "France", "city": "Paris"}]
