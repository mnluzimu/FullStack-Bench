import json
from datetime import datetime, date
from pathlib import Path
from collections.abc import Mapping, Sequence

def to_jsonable(obj):
    """
    Recursively convert *obj* so that the result can be passed to
    json.dump()/json.dumps() without raising “Object of type … is not JSON
    serializable”.

    Rules
    -----
    1. JSON-native primitives (str, int, float, bool, None) are returned as-is.
    2. datetime / date ➜ ISO-8601 string.
    3. dict-like ➜ dict whose *keys are strings* and whose values were processed
       recursively.
    4. list / tuple / set ➜ list whose elements were processed recursively.
    5. bytes / bytearray ➜ UTF-8 string (with replacement on errors).
    6. Anything else ➜ str(obj).
    """
    # 1 ── primitives ───────────────────────────────────────────────────────
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj

    # 2 ── dates & times ────────────────────────────────────────────────────
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()

    # 3 ── mappings (dict, defaultdict, OrderedDict, …) ─────────────────────
    if isinstance(obj, Mapping):
        return {str(k): to_jsonable(v) for k, v in obj.items()}

    # 4 ── sequences / sets (but *not* strings or bytes) ────────────────────
    if isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
        return [to_jsonable(x) for x in obj]
    if isinstance(obj, set):
        return [to_jsonable(x) for x in obj]

    # 5 ── binary blobs ─────────────────────────────────────────────────────
    if isinstance(obj, (bytes, bytearray)):
        return obj.decode("utf-8", errors="replace")

    # 6 ── pathlib.Path ─────────────────────────────────────────────────────
    if isinstance(obj, Path):
        return str(obj)

    # 7 ── fallback ─────────────────────────────────────────────────────────
    return str(obj)