import csv
import json
from pathlib import Path


def read_prompts(path):
    source = Path(path)
    suffix = source.suffix.lower()
    result = []
    if suffix == ".txt":
        # One non-empty line per prompt. A blank line separates paragraphs if present.
        content = source.read_text(encoding="utf-8-sig")
        result = [p.strip() for p in content.split("\n\n") if p.strip()]
        if len(result) == 1:
            result = [p.strip() for p in content.splitlines() if p.strip()]
    elif suffix == ".csv":
        with source.open("r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))
        if rows:
            idx = next((i for i, v in enumerate(rows[0]) if v.strip().lower() in
                       {"prompt", "description", "mô tả", "noi dung", "nội dung"}), 0)
            has_header = any(v.strip().lower() in {"prompt", "description", "mô tả", "nội dung"} for v in rows[0])
            result = [row[idx].strip() for row in rows[1 if has_header else 0:] if len(row) > idx and row[idx].strip()]
    elif suffix in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook
        wb = load_workbook(source, read_only=True, data_only=True)
        try:
            rows = iter(wb.active.iter_rows(values_only=True))
            header = next(rows, [])
            idx = next((i for i, x in enumerate(header) if str(x or "").strip().lower()
                       in {"prompt", "description", "mô tả", "nội dung"}), 0)
            has_header = any(str(x or "").strip().lower() in
                             {"prompt", "description", "mô tả", "nội dung"} for x in header)
            if not has_header and len(header) > idx and header[idx]:
                result.append(str(header[idx]).strip())
            for row in rows:
                if len(row) > idx and row[idx] is not None:
                    text = str(row[idx]).strip()
                    if text:
                        result.append(text)
        finally:
            wb.close()
    elif suffix == ".json":
        contents = json.loads(source.read_text(encoding="utf-8-sig"))
        if not isinstance(contents, list):
            raise ValueError("File JSON phải là danh sách prompts.")
        result = [str(x.get("prompt") or x.get("description") or "").strip() if isinstance(x, dict)
                  else str(x).strip() for x in contents]
    else:
        raise ValueError("Hỗ trợ TXT, CSV, XLSX, XLSM hoặc JSON.")
    return [item for item in result if item]
