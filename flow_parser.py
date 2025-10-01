import json
import sys

# load flow.json with error handling
def load_flow(path):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: file not found: {path}", file=sys.stderr)
        return None
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON in {path}: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error: failed to read {path}: {e}", file=sys.stderr)
        return None

# build a quick index from step id -> full step object
def index_steps_by_id(steps):
    idx = {}
    for s in steps or []:
        if isinstance(s, dict) and s.get("id"):
            idx[s["id"]] = s
    return idx

# extract only relevant metadata for quick reference
def extract_meta(flow):
    return {
        "name": flow.get("name"),
        "useCase": flow.get("useCase"),
        "schemaVersion": flow.get("schemaVersion"),
        "description": flow.get("description"),
        "status": flow.get("status"),
        "created": flow.get("created"),
    }

# extract CHAPTER steps (titles/subtitles) for summaries
def extract_chapters(steps):
    chapters = []
    for s in steps or []:
        if s.get("type") == "CHAPTER":
            chapters.append({
                "id": s.get("id"),
                "title": s.get("title"),
                "subtitle": s.get("subtitle"),
            })
    return chapters

# extract core fields from steps (IMAGE/VIDEO context + clicks/hotspots)
def extract_steps(steps):
    out = []
    for s in steps or []:
        item = {"id": s.get("id"), "type": s.get("type")}
        t = s.get("type")

        if t in ("IMAGE", "VIDEO"):
            page = s.get("pageContext") or {}
            click = s.get("clickContext") or {}
            hotspots = s.get("hotspots") or []

            item["pageTitle"] = page.get("title")
            item["pageUrl"] = page.get("url")

            if click:
                item["clickText"] = click.get("text")
                item["clickSelector"] = click.get("cssSelector")
                item["clickElementType"] = click.get("elementType")

            labels = []
            for h in hotspots:
                if isinstance(h, dict) and h.get("label"):
                    labels.append(h.get("label"))
            if labels:
                item["hotspotLabels"] = labels

        elif t == "CHAPTER":
            item["title"] = s.get("title")
            item["subtitle"] = s.get("subtitle")

        out.append(item)
    return out

# build the final summary object
def build_report(flow):
    steps = flow.get("steps") or []
    step_index = index_steps_by_id(steps)

    return {
        "meta": extract_meta(flow),
        "chapters": extract_chapters(steps),
        "steps": extract_steps(steps),
    }

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "flow.json"

    data = load_flow(path)
    if data is None:
        sys.exit(1)

    report = build_report(data)
    try:
        print(json.dumps(report, indent=2))
    except Exception as e:
        print(f"Error: failed to serialize report: {e}", file=sys.stderr)
        sys.exit(1)