import json
import sys
import os
import base64
import requests
import hashlib
import shutil

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

# on-disk caching helpers (opt-in via ENABLE_CACHE=1)
def get_cache_dir():
    return os.path.join(".cache")

def ensure_cache_dir():
    try:
        os.makedirs(get_cache_dir(), exist_ok=True)
    except Exception:
        pass

def make_cache_key(text):
    content = (text or "").encode("utf-8")
    return hashlib.sha256(content).hexdigest()[:16]

# shared helpers
def is_cache_enabled():
    return os.getenv("ENABLE_CACHE", "1") == "1"

def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY is not set in environment.", file=sys.stderr)
        return None
    try:
        from openai import OpenAI
        return OpenAI()
    except Exception as e:
        print(f"Error: failed to import OpenAI client: {e}", file=sys.stderr)
        return None

def derive_actions(report):
    steps = report.get("steps") or []
    action_lines = []
    actions = []
    for s in steps:
        step_type = s.get("type")
        click_text = s.get("clickText")
        title = s.get("pageTitle") or s.get("title")
        if step_type == "CHAPTER" and title:
            action_lines.append(f"CHAPTER: {title}")
        elif click_text:
            action_lines.append(f"{step_type}: {click_text}")
            actions.append(click_text)
        else:
            action_lines.append(f"{step_type}: {title}" if title else str(step_type))
    return action_lines, actions

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
    try:
        client = get_openai_client()
        if client is None:
            return None

        meta = report.get("meta") or {}
        action_lines, _ = derive_actions(report)

        # cap context at 25 actions to limit cost
        joined_actions = "\n".join(action_lines[:25])

        # caching (summary)
        enable_cache = is_cache_enabled()
        cache_key = make_cache_key((meta.get('name') or '') + "\n" + joined_actions + "\n" + "gpt-4o-mini")
        cache_path = os.path.join(get_cache_dir(), f"summary-{cache_key}.md")
        if enable_cache and os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    return f.read().strip()
            except Exception:
                pass

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

        # write to cache
        if enable_cache:
            ensure_cache_dir()
            try:
                with open(cache_path, "w", encoding="utf-8") as f:
                    f.write(summary)
            except Exception:
                pass

        return summary

    except Exception as e:
        print(f"Error: OpenAI request failed: {e}", file=sys.stderr)
        return None

# generate social media image
def generate_social_image(report, out_path="output/flow_social_image.png"):
    try:
        client = get_openai_client()
        if client is None:
            return False

        meta = report.get("meta") or {}

        # build minimal context for image generation
        name = meta.get("name") or "User Flow"

        # extract key actions
        _, actions = derive_actions(report)
        actions_summary = ", ".join(actions[:5]) if actions else "browsing and interacting"

        # prompt that uses flow metadata
        prompt = (
            f"Create a vibrant, professional social media graphic for a product demo titled '{name}'. "
            f"The visual should represent a compilation of actions like: {actions_summary}. "
            f"Use modern UI/UX design elements, clean layout, and engaging colors. "
            f"Style: matching the flow's theme, professional, tech-focused. No text overlay needed."
        )

        # caching (image)
        enable_cache = is_cache_enabled()
        cache_key = make_cache_key(prompt + "\n" + "gpt-image-1")
        cache_path = os.path.join(get_cache_dir(), f"image-{cache_key}.png")
        if enable_cache and os.path.exists(cache_path):
            try:
                out_dir = os.path.dirname(out_path) or "."
                os.makedirs(out_dir, exist_ok=True)
                shutil.copyfile(cache_path, out_path)
                return True
            except Exception:
                pass

        # generate image using optimal model
        response = client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            background="opaque"
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
                if enable_cache:
                    ensure_cache_dir()
                    try:
                        with open(cache_path, "wb") as cf:
                            cf.write(img_bytes)
                    except Exception:
                        pass
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
                if enable_cache:
                    ensure_cache_dir()
                    try:
                        shutil.copyfile(out_path, cache_path)
                    except Exception:
                        pass
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