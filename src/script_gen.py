import json
import requests


def _generate_with_openai(topic: str, target_minutes: int, api_key: str, model: str) -> str:
    prompt = (
        f"Write a {target_minutes}-minute YouTube script for a faceless channel called AI Cash Lab.\n"
        f"Topic: I tried {topic} for 7 days.\n"
        "Style: documentary experiment, realistic, not guru/scam.\n"
        "Use short paragraphs and clear section headers.\n"
        "Include: hook, setup, tools, day-by-day, results with numbers, analysis, scaling plan, verdict, CTA.\n"
        "Output only the final script text in plain text.\n"
    )

    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "temperature": 0.7,
            "messages": [
                {
                    "role": "system",
                    "content": "You are an expert YouTube scriptwriter for faceless business channels.",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
        },
        timeout=90,
    )
    r.raise_for_status()
    data = r.json()
    return (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )


def _generate_with_ollama(topic: str, target_minutes: int, ollama_base_url: str, ollama_model: str) -> str:
    prompt = (
        f"Write a {target_minutes}-minute YouTube script for a faceless channel called AI Cash Lab.\n"
        f"Topic: I tried {topic} for 7 days.\n"
        "Style: documentary experiment, realistic, not guru/scam.\n"
        "Use short paragraphs and clear section headers.\n"
        "Include: hook, setup, tools, day-by-day, results with numbers, analysis, scaling plan, verdict, CTA.\n"
        "Avoid copyrighted brand claims. Keep it clean and engaging.\n"
    )

    r = requests.post(
        f"{ollama_base_url}/api/generate",
        json={"model": ollama_model, "prompt": prompt, "stream": False},
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    return (data.get("response") or "").strip()

def _fallback_script(topic: str, target_minutes: int) -> str:
    # ~150 wpm narration
    target_words = target_minutes * 150
    base = f"""
TITLE: I Tried {topic} for 7 Days — Here’s What Happened

HOOK:
People claim you can make money fast using AI and marketplaces like Etsy. So I tested it for 7 days from scratch.

SECTION 1 — What this side hustle is
Explain what the hustle is, why people believe it works, and what “digital products” are.

SECTION 2 — Tools used
Explain using AI to generate templates, editing with Canva, and how Etsy listings work.

SECTION 3 — The 7-day plan
Describe Day 1 setup, Day 2-3 improving listings, Day 4-5 first traction, Day 6-7 results.

SECTION 4 — Results
Give realistic numbers: views, favorites, sales, revenue. Explain it’s not instant riches, but it proves demand.

SECTION 5 — What I’d do to scale
Volume of listings, niche focus, better thumbnails/previews, bundles, keyword research.

VERDICT:
Worth trying if you treat it like a volume game. Subscribe for the next experiment.
"""
    # Expand by repetition with varied phrasing to reach target length
    blocks = [base.strip()]
    while len(" ".join(blocks).split()) < target_words:
        blocks.append(
            f"\n\nSCALING TIP:\nHere’s another practical way to scale {topic}: improve listing keywords, offer bundles, and test pricing.\n"
            f"Add a short example and a mini-case study style paragraph about what happened on Day {len(blocks)+1}."
        )
    return "\n".join(blocks)

def generate_script(
    topic: str,
    target_minutes: int,
    ollama_base_url: str,
    ollama_model: str,
    openai_api_key: str = "",
    openai_model: str = "gpt-4o-mini",
    provider: str = "auto",
) -> str:
    """Generate script using GPT or Ollama, then fallback to local template."""
    candidates = []

    if provider == "gpt":
        candidates = ["gpt"]
    elif provider == "ollama":
        candidates = ["ollama"]
    else:
        candidates = ["gpt", "ollama"]

    for candidate in candidates:
        try:
            if candidate == "gpt" and openai_api_key:
                text = _generate_with_openai(topic, target_minutes, openai_api_key, openai_model)
            elif candidate == "ollama":
                text = _generate_with_ollama(topic, target_minutes, ollama_base_url, ollama_model)
            else:
                continue

            if len(text.split()) >= max(350, target_minutes * 110):
                return text
        except Exception:
            continue

    return _fallback_script(topic, target_minutes)