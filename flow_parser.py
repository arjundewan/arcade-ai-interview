import json
import sys
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

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

# write summary to markdown file
def write_summary_to_file(summary_text, out_path="output/flow_summary.md"):
    try:
        # ensure output directory exists
        out_dir = os.path.dirname(out_path) or "."
        os.makedirs(out_dir, exist_ok=True)

        # write markdown content
        with open(out_path, "w", encoding="utf-8") as f:
            f.write((summary_text or "").strip() + "\n")
        return True
    except Exception as e:
        print(f"Error: failed to write summary to {out_path}: {e}", file=sys.stderr)
        return False

# call OpenAI to produce brief summary of interactions
def generate_openai_summary(report):
    # get OpenAI API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY is not set in environment.", file=sys.stderr)
        return None

    try:
        from openai import OpenAI
    except Exception as e:
        print(f"Error: failed to import OpenAI client: {e}", file=sys.stderr)
        return None

    try:
        client = OpenAI()

        meta = report.get("meta") or {}
        steps = report.get("steps") or []

        # build a compact description of the interactions
        action_lines = []
        for s in steps:
            t = s.get("type")
            click_text = s.get("clickText")
            title = s.get("pageTitle") or s.get("title")
            if t == "CHAPTER" and title:
                action_lines.append(f"CHAPTER: {title}")
            elif click_text:
                action_lines.append(f"{t}: {click_text}")
            else:
                # fallback to type + page title, if available
                if title:
                    action_lines.append(f"{t}: {title}")
                else:
                    action_lines.append(str(t))

        # cap context at 25 actions to limit cost
        joined_actions = "\n".join(action_lines[:25])

        system_prompt = (
            """You are a helpful assistant that analyzes user product flows.

            You will be provided with a name, use case, metadata, and a list of ordered actions that the user took.
            Your task is to first provide a summary of the the user's goal and what they did based on the actions.
            Then, you will list all of the user's actions in order in a human readable format (e.g.  (i.e. "Clicked on checkout", "Search for X").
            
            Be clear, friendly, and avoid redundancy.
            Be sure to output your response in markdown format."""
        )
        user_prompt = (
            f"Name: {meta.get('name')}\n"
            f"Use Case: {meta.get('useCase')}\n\n"
            "Actions (ordered):\n"
            f"{joined_actions}"
        )

        # use small but sufficient model
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=400,
        )

        try:
            summary = (resp.choices[0].message.content or "").strip()
        except Exception:
            summary = ""

        if not summary:
            print("Error: received empty summary from OpenAI.", file=sys.stderr)
            return None

        return summary

    except Exception as e:
        print(f"Error: OpenAI request failed: {e}", file=sys.stderr)
        return None

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "flow.json"

    data = load_flow(path)
    if data is None:
        sys.exit(1)

    # build the report
    report = build_report(data)

    # generate summary of the report
    summary = generate_openai_summary(report)

    # decide output path
    output_path = os.path.join("output", "flow_summary.md")

    if summary:
        ok = write_summary_to_file(summary, output_path)
        if ok:
            print(f"\n✓ Summary written to {output_path}")
    else:
        print("\n(Note) OpenAI summary not available.")
        placeholder = "# Flow Summary\n\nOpenAI summary not available. See stderr for details."
        write_summary_to_file(placeholder, output_path)