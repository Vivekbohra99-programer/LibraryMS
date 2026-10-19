"""Export service – CSV and Excel generation.

Spreadsheet programs treat a cell that starts with = + - or @ as a formula. Book titles, member names and
log details are typed by users, so an export could carry a formula that runs when a librarian opens the file
(CSV injection). Both writers neutralise that: CSV cells get a leading apostrophe, Excel cells are stored as
plain text."""
import csv
import io
import re
from openpyxl import Workbook

_FORMULA_STARTS = ('=', '+', '-', '@', '\t', '\r')
_PHONE_LIKE = re.compile(r'^\+?[0-9][0-9\s\-().]*$')       # +91 98765-43210 is data, not a formula


def _needs_guard(value):
    return isinstance(value, str) and value.startswith(_FORMULA_STARTS) and not _PHONE_LIKE.match(value)


def _csv_safe(value):
    return "'" + value if _needs_guard(value) else value


def to_csv(headers, rows):
    """Return CSV content as a string."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in rows:
        writer.writerow([_csv_safe(v) for v in row])
    return output.getvalue()


def to_excel(headers, rows, sheet_name='Sheet1'):
    """Return Excel content as bytes."""
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws.append(headers)
    for row in rows:
        ws.append(list(row))
    for excel_row in ws.iter_rows(min_row=2):
        for cell in excel_row:
            if cell.data_type == 'f':          # openpyxl stores any text beginning with '=' as a formula
                cell.data_type = 's'
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue()
