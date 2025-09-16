from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any

app = FastAPI(title="SmartForm Parser API")


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
    page_set = set()
    window_set = set()
    field_set = set()
    table_set = set()

    for row in rows:
        elem = row.get("ELEM_NAME", "").strip()
        text = row.get("TEXT_PAYLOAD", "").strip()
        node = row.get("NODE_TYPE", "").strip()

        # Pages
        if elem == "INAME" and text.startswith("%PAGE"):
            page_set.add(text)

        # Windows
        if node == "ELEMENT" and elem == "INAME" and text.upper() == "MAIN":
            window_set.add(text)

        # Captions / Field names (keep unique)
        if elem in ["CAPTION", "FORMNAME", "NAME", "TYPENAME"]:
            key = f"{elem}:{text}"
            field_set.add(key)

        # Tables (heuristic: TYPE names starting with T or containing TABLE/TAB)
        if elem == "TYPENAME" and ("T" in text or "TAB" in text.upper()):
            table_set.add(text)

    # Convert back to list of dicts
    pages = [{"page_name": p} for p in sorted(page_set)]
    windows = [{"window_name": w} for w in sorted(window_set)]
    fields = [{k.split(":", 1)[0]: k.split(":", 1)[1]} for k in sorted(field_set)]
    tables = [{"table_type": t} for t in sorted(table_set)]

    return {
        "pages": pages,
        "windows": windows,
        "fields": fields,
        "tables": tables,
    }


# --- API Endpoint ---
@app.post("/parse-smartform/")
async def parse_smartform_api(rows: List[SmartformRow]):
    try:
        parsed = parse_smartform([row.dict() for row in rows])
        return parsed
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
