from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
import re

app = FastAPI(title="SmartForm Parser API with Page-Window Structure")


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
    pages = []
    current_page = None
    current_window = None
    # current_graphic = None
    capture_page = False
    capture_window = False
    # capture_graphic = False
    last_page_name = None
    code_buffer = [] 
    capture_test_block = False


    for row in rows:
        elem = row.get("ELEM_NAME", "")
        text = (row.get("TEXT_PAYLOAD", "") or "").strip()
        node = row.get("NODE_TYPE", "")

        # --- Detect Page ---
        if elem == "NODETYPE" and text == "PA":
            capture_page = True
            continue

        if capture_page and elem == "INAME":
            clean_name = text.lstrip("%")   # <-- remove leading %
            if clean_name != last_page_name:  # prevent duplicate page entries
                current_page = {"page_name": clean_name, "windows": []}
                pages.append(current_page)
                last_page_name = text
            current_window = None
            capture_page = False
            continue

        # --- Detect Window Marker ---
        if elem == "NODETYPE" and text == "WI":
            capture_window = True
            continue

        if capture_window and elem == "INAME":
            clean_name = text.lstrip("%")   # <-- remove leading %
            current_window = {
                "window_name": clean_name,
                "rows": [],
                "cells": [],
                "texts": [],
                "code": [],
                "captions": [],
                "fields": [],
                "tables": [],
                "_captions_set": set(),
                "_fields_set": set(),
                "_tables_set": set(),
            }
            if current_page:
                current_page["windows"].append(current_window)
            capture_window = False
            continue

        # --- NEW: Detect start of TEST block ---
        if elem == "INAME" and text.startswith("%TEXT"):
            capture_test_block = True
            continue

        # --- Stop collecting when STYLE_NAME appears ---
        if capture_test_block and elem == "STYLE_NAME":
            capture_test_block = False
            continue

        # --- Collect TDLINE lines if inside TEST block ---
        if capture_test_block and elem == "TDLINE" and text:
            if current_window:
                current_window["texts"].append(text)
            continue

        # --- Classify & extract inside current window ---
        if current_window and not capture_test_block:
            # Captions / Names
            if elem in ["CAPTION", "FORMNAME", "NAME", "TYPENAME"] and text:
                current_window["_captions_set"].add(f"{elem}:{text}")

            # Detect tables from SQL
            select_tables = re.findall(r"\bFROM\s+([A-Za-z0-9_./]+)", text, re.IGNORECASE)
            for t in select_tables:
                current_window["_tables_set"].add(t.upper())

            # Workarea fields
            workarea_fields = re.findall(r"\b([A-Za-z0-9_]+)-([A-Za-z0-9_]+)\b", text)
            for wa, field in workarea_fields:
                current_window["_fields_set"].add(f"{wa.upper()}-{field.upper()}")

            # Tables from TYPE references
            if elem == "TYPENAME" and ("T" in text or "TAB" in text.upper()):
                current_window["_tables_set"].add(text)

            # Structural classification
            if text.startswith("%ROW"):
                current_window["rows"].append(text)
            elif text.startswith("%CELL"):
                current_window["cells"].append(text)
            elif text.startswith("%TEXT"):
                current_window["texts"].append(text)
            elif elem == "item" and text:  # only ELEM_NAME = item goes into code
                cleaned_lines = []
                for line in text.splitlines():
                    line = line.strip()
                    if line.startswith("*"):  # full-line comment
                        continue
                    if '"' in line:  # inline comment
                        line = line.split('"', 1)[0].rstrip()
                    if line:  # only keep non-empty code lines
                        cleaned_lines.append(line)
                if cleaned_lines:
                    code_buffer.append("\n".join(cleaned_lines))
                # code_buffer.append(text)
            else:
                if code_buffer:  # flush when ITEM block ends
                    current_window["code"].append("\n".join(code_buffer))
                    code_buffer = []
    # Finalize sets -> lists
    # after loop, flush if last rows were ITEMs
    if code_buffer and current_window:
        current_window["code"].append("\n".join(code_buffer))
    for page in pages:
        for win in page.get("windows", []):
            # win["captions"] = sorted(win.pop("_captions_set"))
            win["captions"] = []
            win["fields"] = sorted(win.pop("_fields_set"))
            win["tables"] = sorted(win.pop("_tables_set"))
            win.pop("_captions_set", None)
    return {"pages": pages}


# --- API Endpoint ---
@app.post("/parse-smartform/")
async def parse_smartform_api(rows: List[SmartformRow]):
    try:
        parsed = parse_smartform([row.dict() for row in rows])
        return parsed
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
