import json
import sys
import os
import base64
import requests

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

# generate social media image
def generate_social_image(report, out_path="output/flow_social_image.png"):
    # get OpenAI API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY is not set in environment.", file=sys.stderr)
        return False

    try:
        from openai import OpenAI
    except Exception as e:
        print(f"Error: failed to import OpenAI client: {e}", file=sys.stderr)
        return False

    try:
        client = OpenAI()

        meta = report.get("meta") or {}
        steps = report.get("steps") or []

        # build minimal context for image generation
        name = meta.get("name") or "User Flow"
        
        # extract key actions
        actions = []
        for s in steps:
            click_text = s.get("clickText")
            if click_text:
                actions.append(click_text)
        
        actions_summary = ", ".join(actions[:5]) if actions else "browsing and interacting"

        # prompt that uses flow metadata
        prompt = (
            f"Create a vibrant, professional social media graphic for a product demo titled '{name}'. "
            f"The visual should represent a compilation of actions like: {actions_summary}. "
            f"Use modern UI/UX design elements, clean layout, and engaging colors. "
            f"Style: matching the flow's theme, professional, tech-focused. No text overlay needed."
        )

        # generate image using optimal model
        response = client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
        )

        # handle base64 or URL payloads for gpt-image-1
        image_data = response.data[0]
        b64_payload = None
        image_url = None

        try:
            # SDK object attributes
            b64_payload = getattr(image_data, "b64_json", None)
            image_url = getattr(image_data, "url", None)
        except Exception:
            pass

        # fallback if dict-like
        if b64_payload is None and isinstance(image_data, dict):
            b64_payload = image_data.get("b64_json")
            image_url = image_data.get("url", image_url)

        out_dir = os.path.dirname(out_path) or "."
        os.makedirs(out_dir, exist_ok=True)

        if b64_payload:
            try:
                img_bytes = base64.b64decode(b64_payload)
                with open(out_path, "wb") as f:
                    f.write(img_bytes)
                return True
            except Exception as decode_err:
                print(f"Error: failed to decode base64 image: {decode_err}", file=sys.stderr)
                return False

        if image_url:
            try:
                with requests.get(image_url, stream=True, timeout=30) as r:
                    r.raise_for_status()
                    with open(out_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                return True
            except Exception as download_err:
                print(f"Error: failed to download image: {download_err}", file=sys.stderr)
                return False

        print("Error: image generation returned no data.", file=sys.stderr)
        return False

    except Exception as e:
        print(f"Error: image generation failed: {e}", file=sys.stderr)
        return False

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "flow.json"

    data = load_flow(path)
    if data is None:
        sys.exit(1)

    # build the report
    report = build_report(data)

    # generate summary of the report
    summary = generate_openai_summary(report)

    # decide output paths
    summary_path = os.path.join("output", "flow_summary.md")
    image_path = os.path.join("output", "flow_social_image.png")

    # write summary
    if summary:
        ok = write_summary_to_file(summary, summary_path)
        if ok:
            print(f"\n✓ Summary written to {summary_path}")
    else:
        print("\n(Note) OpenAI summary not available.")
        placeholder = "# Flow Summary\n\nOpenAI summary not available. See stderr for details."
        write_summary_to_file(placeholder, summary_path)

    # generate social media image
    if generate_social_image(report, image_path):
        print(f"✓ Social image written to {image_path}")