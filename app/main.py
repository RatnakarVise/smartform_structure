from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
import re

app = FastAPI(title="SmartForm Parser API with ABAP Code Parsing")


# --- Request Model ---
class SmartformRow(BaseModel):
    ID: int
    PARENT_ID: int
    DEPTH: int
    PATH: str
    ELEM_NAME: str
    ELEM_NS: str
    NODE_TYPE: str
    ATTRIBUTES: List[Any]
    TEXT_PAYLOAD: str


# --- Parser Logic ---
def parse_smartform(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    pages = set()
    windows = set()
    fields = set()
    tables = set()

    capture_window = False  # flag to capture INAME after WI

    for row in rows:
        elem = row.get("ELEM_NAME", "")
        text = row.get("TEXT_PAYLOAD", "") or ""
        node = row.get("NODE_TYPE", "")

        # --- 1. Pages ---
        if elem == "INAME" and text.startswith("%PAGE"):
            pages.add(text)

        # --- 2. Detect window marker (NODETYPE = WI) ---
        if elem == "NODETYPE" and text == "WI":
            capture_window = True
            continue

        if capture_window and elem == "INAME":
            windows.add(text)
            capture_window = False

        # --- 3. Captions / Names directly from nodes ---
        if elem in ["CAPTION", "FORMNAME", "NAME", "TYPENAME"]:
            fields.add(f"{elem}:{text}")

        # --- 4. Detect TABLES in ABAP code ---
        select_tables = re.findall(r"\bFROM\s+([A-Za-z0-9_/]+)", text, re.IGNORECASE)
        for t in select_tables:
            tables.add(t.upper())

        # --- 5. Detect fields from work areas (pattern: wa-field) ---
        workarea_fields = re.findall(r"\b([A-Za-z0-9_]+)-([A-Za-z0-9_]+)", text)
        for wa, field in workarea_fields:
            fields.add(f"{wa.upper()}-{field.upper()}")

        # --- 6. Tables from TYPE references ---
        if elem == "TYPENAME" and ("T" in text or "TAB" in text.upper()):
            tables.add(text)

    return {
        "pages": [{"page_name": p} for p in sorted(pages)],
        "windows": [{"window_name": w} for w in sorted(windows)],
        "fields": [{"field": f} for f in sorted(fields)],
        "tables": [{"table_type": t} for t in sorted(tables)],
    }


# --- API Endpoint ---
@app.post("/parse-smartform/")
async def parse_smartform_api(rows: List[SmartformRow]):
    try:
        parsed = parse_smartform([row.dict() for row in rows])
        return parsed
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
