import os
import re
import json
import time
import argparse
import logging
from typing import Dict, Any, Optional, List

from dotenv import load_dotenv
from anthropic import Anthropic

# Configure logging similarly to other modules
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Load environment variables at import time for CLI and function usage
load_dotenv()

PREFERRED_MODEL = "claude-3-5-sonnet-20240620"
FALLBACK_MODEL = "claude-3-haiku-20240307"


def _ensure_api_key() -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not found in environment variables")
        raise ValueError("ANTHROPIC_API_KEY not found in environment variables")
    return api_key


def _build_system_prompt() -> str:
    return (
        "You are a careful, non‑partisan summarizer for civic education.\n"
        "**Your output must be STRICT JSON with two keys only: `tweet` and `long`. No code fences. No extra text.**\n\n"
        "**General rules:**\n"
        "- Do not invent facts or numbers. Only use information present in the provided bill data.\n"
        "- Keep summaries clear, neutral, and accessible for a teen civic audience.\n"
        "- Avoid partisan framing, speculation, or “supporters say/critics say” constructions.\n\n"
        "**tweet (short summary):**\n"
        "- One professional, factual sentence ≤200 characters.\n"
        "- Highlight the major priorities or themes of the bill (e.g., expands surveillance, cuts environmental rules, boosts science funding, regulates AI).\n"
        "- Emphasize broad trends or impacts people could react to, and an example from the bill (e.g., “shifts funding toward law enforcement,” “adds new restrictions on abortion,” “expands federal role in online privacy”).\n"
        "- Avoid getting lost in raw dollar amounts or minor procedural details (e.g., “Union Calendar”).\n"
        "- Use stage‑appropriate verbs:\n"
        "  - “proposes” if newly introduced.\n"
        "  - “passed House/Senate” if advanced.\n"
        "  - “sent to President” if delivered.\n"
        "  - “became law” once enacted.\n"
        "- No emojis, hashtags, or fluff. Always a clean, complete sentence.\n"
        "- Use acronyms only if they are universally recognized (NASA, FBI); otherwise spell them out.\n\n"
        "**long (detailed summary):**\n"
        "- Start with an **Overview**: 2–3 plain‑English sentences explaining what the bill does and why it matters.\n"
        "- Then provide a concise, factual breakdown in a single string that:\n"
        "  - Summarizes the bill’s **major provisions** (programs created, agencies affected, funding levels if given, or policy changes).\n"
        "  - Notes any **conditions, restrictions, or policy riders** that shape how money or authority is used.\n"
        "  - Explains the **bill’s current stage in the legislative process** (introduced, committee, calendar, passed, etc.).\n"
        "  - Defines acronyms on first use (e.g., “DEA = Drug Enforcement Administration”).\n"
        "- Keep tone factual, neutral, and civic‑friendly.\n\n"
        "**Output format (strict JSON):**\n"
        '{"tweet": "...", "long": "..."}'
    )


def _build_user_prompt(bill: Dict[str, Any]) -> str:
    bill_json = json.dumps(bill, ensure_ascii=False)

    # Include full text if available, with NO truncation
    full_text_section = ""
    if bill.get("full_text"):
        try:
            tf = bill.get("text_format")
            tu = bill.get("text_url")
            ft = bill["full_text"]
            logger.info(f"include_text=True; using attached full_text (no truncation). chars={len(ft)}; text_format={tf}; text_url={tu}")
            full_text_section = f"\n\nFull bill text (no truncation):\n{ft}"
        except Exception as e:
            logger.warning(f"Error while building full_text section: {e}")

    user_prompt = (
        "Summarize the following bill object under the constraints above.\n"
        "Return ONLY a strict JSON object with keys 'tweet' and 'long'.\n"
        f"Bill JSON:\n{bill_json}{full_text_section}"
    )
    logger.info(f"User prompt char count: {len(user_prompt)}")
    return user_prompt


def _extract_text_from_response(resp) -> str:
    # Anthropics messages API returns a list of content blocks; join their text
    parts: List[str] = []
    for block in getattr(resp, "content", []) or []:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts).strip()


def _strip_code_fences(text: str) -> str:
    t = text.strip()
    # Remove leading/trailing triple backticks optionally annotated with language
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9]*\s*", "", t, flags=re.DOTALL)
    if t.endswith("```"):
        t = re.sub(r"\s*```$", "", t, flags=re.DOTALL)
    return t.strip()


def _sanitize_json_text(text: str) -> str:
    """
    Remove control characters and other non-printable characters that might break JSON parsing.
    Keeps common whitespace characters (space, tab, newline, carriage return).
    """
    # Remove control characters except for common whitespace: \t, \n, \r
    cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
    # Additionally remove any other non-printable Unicode characters
    cleaned = re.sub(r'[^\x20-\x7E\x0A\x0D\x09]', '', cleaned)
    return cleaned

def _try_parse_json_strict(text: str) -> Dict[str, Any]:
    t = _strip_code_fences(text)
    t = _sanitize_json_text(t)
    # First attempt: direct JSON parse
    try:
        return json.loads(t)
    except Exception:
        pass
    # Fallback: extract the largest JSON object substring between first { and last }
    first = t.find("{")
    last = t.rfind("}")
    if first != -1 and last != -1 and last > first:
        cand = t[first : last + 1]
        try:
            return json.loads(cand)
        except Exception:
            pass
    # If still failing, last attempt: remove any leading BOM or stray characters before { and after }
    t2 = re.sub(r"^[^\{]*", "", t)
    t2 = re.sub(r"[^\}]*$", "", t2)
    return json.loads(t2)  # Let this raise for caller


def _smart_truncate_tweet(tweet: str, limit: int = 200) -> str:
    # Legacy helper (kept for backward-compat). We now prefer coherent tightening without ellipsis.
    t = tweet.strip()
    if len(t) <= limit:
        return t
    cut = t[:limit].rstrip()
    # Prefer cutting at sentence boundary
    for p in [".", "!", "?"]:
        idx = cut.rfind(p)
        if idx != -1 and idx >= 60:
            return cut[: idx + 1]
    # Else cut at last space and add period if needed
    sp = cut.rfind(" ")
    if sp >= 60:
        cut = cut[:sp].rstrip()
    if not cut.endswith((".", "!", "?")):
        cut += "."
    return cut[:limit]


def _call_anthropic_once(client: Anthropic, model: str, system: str, user: str):
    return client.messages.create(
        model=model,
        max_tokens=800,
        temperature=0.2,
        system=system,
        messages=[{"role": "user", "content": [{"type": "text", "text": user}]}],
    )


def _model_call_with_fallback(client: Anthropic, system: str, user: str) -> str:
    """
    Call Anthropic with preferred then fallback model.
    Includes simple exponential backoff on 429 rate_limit errors.
    """
    last_err: Optional[Exception] = None
    for model in (PREFERRED_MODEL, FALLBACK_MODEL):
        delay = 1.0
        for attempt in range(1, 4):
            try:
                logger.info(f"Calling Anthropic model: {model}")
                resp = _call_anthropic_once(client, model, system, user)
                text = _extract_text_from_response(resp)
                if text:
                    return text
                else:
                    last_err = RuntimeError("Empty response content")
                    logger.warning(f"Empty response for {model} (attempt {attempt})")
            except Exception as e:
                last_err = e
                emsg = str(e).lower()
                if "429" in emsg or "rate_limit" in emsg:
                    logger.info(f"429/rate limit for {model}; sleeping {delay:.2f}s then retrying (attempt {attempt}/3)")
                    time.sleep(delay)
                    delay *= 2.0
                    continue
                logger.warning(f"Model call failed for {model} (attempt {attempt}): {e}")
                break  # move to next model
    if last_err:
        raise last_err
    raise RuntimeError("No response from Anthropic")


def _ensure_period(s: str) -> str:
    s = s.strip()
    if not s:
        return s
    if not s.endswith((".", "!", "?")):
        s += "."
    return s


def _tighten_tweet_heuristic(text: str, limit: int = 200) -> str:
    # Non-ellipsis heuristic compressor that aims to keep a complete sentence.
    t = re.sub(r"\s+", " ", text.strip())
    # Space-saving substitutions (lightweight, neutral)
    t = re.sub(r"\b[Cc]ongress and\b", "Congress &", t)
    t = re.sub(r"\band\b", "&", t)
    # If within limit already, just ensure clean end.
    if len(t) <= limit:
        return _ensure_period(t)
    # Try sentence boundary within limit
    cut = t[:limit]
    for p in [".", "!", "?"]:
        idx = cut.rfind(p)
        if idx != -1 and idx >= 60:
            return cut[: idx + 1].strip()
    # Otherwise cut at last space, clean trailing punctuation, end with period
    sp = cut.rfind(" ")
    if sp >= 60:
        cut = cut[:sp]
    cut = cut.rstrip(",;:- ")
    return _ensure_period(cut)


def _tighten_tweet_model(client: Anthropic, raw_tweet: str, bill: Dict[str, Any], limit: int = 200) -> str:
    system = (
        "Rewrite the provided headline into a single complete sentence suitable for X/Twitter.\n"
        f"- ≤ {limit} characters.\n"
        "- No emojis, no hashtags, no ellipsis.\n"
        "- Professional, factual, impact-focused.\n"
        "- Use stage-appropriate verbs: if newly introduced, prefer 'proposes'; if 'passed House'/'passed Senate', say that; if sent to President or became law, state it plainly.\n"
        "Return ONLY the sentence text."
    )
    user = (
        "Original tweet draft:\n"
        f"{raw_tweet}\n\n"
        "Bill context (JSON):\n"
        f"{json.dumps(bill, ensure_ascii=False)}"
    )
    # Use preferred/fallback model pipeline to rewrite
    rewritten = _model_call_with_fallback(client, system, user)
    # The rewrite returns plain text (not JSON here)
    tightened = rewritten.strip().strip("`")
    # Hard guarantee: enforce length and clean ending
    if len(tightened) > limit:
        tightened = _tighten_tweet_heuristic(tightened, limit=limit)
    else:
        tightened = _ensure_period(tightened)
    return tightened


def _coherent_tighten_tweet(client: Anthropic, raw_tweet: str, bill: Dict[str, Any], limit: int = 200) -> str:
    if len(raw_tweet.strip()) <= limit and raw_tweet.strip():
        return _ensure_period(raw_tweet)
    try:
        return _tighten_tweet_model(client, raw_tweet, bill, limit=limit)
    except Exception as e:
        logger.warning(f"Model tighten failed, using heuristic tightening: {e}")
        return _tighten_tweet_heuristic(raw_tweet, limit=limit)


def _ensure_period(s: str) -> str:
    s = s.strip()
    if not s:
        return s
    if not s.endswith((".", "!", "?")):
        s += "."
    return s


def _tighten_tweet_heuristic(text: str, limit: int = 200) -> str:
    # Non-ellipsis heuristic compressor that aims to keep a complete sentence.
    t = re.sub(r"\s+", " ", text.strip())
    # Space-saving substitutions (lightweight, neutral)
    t = re.sub(r"\b[Cc]ongress and\b", "Congress &", t)
    t = re.sub(r"\band\b", "&", t)
    # If within limit already, just ensure clean end.
    if len(t) <= limit:
        return _ensure_period(t)
    # Try sentence boundary within limit
    cut = t[:limit]
    for p in [".", "!", "?"]:
        idx = cut.rfind(p)
        if idx != -1 and idx >= 60:
            return cut[: idx + 1].strip()
    # Otherwise cut at last space, clean trailing punctuation, end with period
    sp = cut.rfind(" ")
    if sp >= 60:
        cut = cut[:sp]
    cut = cut.rstrip(",;:- ")
    return _ensure_period(cut)


def _tighten_tweet_model(client: Anthropic, raw_tweet: str, bill: Dict[str, Any], limit: int = 200) -> str:
    system = (
        "Rewrite the provided headline into a single complete sentence suitable for X/Twitter.\n"
        f"- ≤ {limit} characters.\n"
        "- No emojis, no hashtags, no ellipsis.\n"
        "- Professional, factual, impact-focused.\n"
        "- Use stage-appropriate verbs: if newly introduced, prefer 'proposes'; if 'passed House'/'passed Senate', say that; if sent to President or became law, state it plainly.\n"
        "Return ONLY the sentence text."
    )
    user = (
        "Original tweet draft:\n"
        f"{raw_tweet}\n\n"
        "Bill context (JSON):\n"
        f"{json.dumps(bill, ensure_ascii=False)}"
    )
    # Use preferred/fallback model pipeline to rewrite
    rewritten = _model_call_with_fallback(client, system, user)
    # The rewrite returns plain text (not JSON here)
    tightened = rewritten.strip().strip("`")
    # Hard guarantee: enforce length and clean ending
    if len(tightened) > limit:
        tightened = _tighten_tweet_heuristic(tightened, limit=limit)
    else:
        tightened = _ensure_period(tightened)
    return tightened


def _coherent_tighten_tweet(client: Anthropic, raw_tweet: str, bill: Dict[str, Any], limit: int = 200) -> str:
    if len(raw_tweet.strip()) <= limit and raw_tweet.strip():
        return _ensure_period(raw_tweet)
    try:
        return _tighten_tweet_model(client, raw_tweet, bill, limit=limit)
    except Exception as e:
        logger.warning(f"Model tighten failed, using heuristic tightening: {e}")
        return _tighten_tweet_heuristic(raw_tweet, limit=limit)
def _repair_pass(client: Anthropic, bill: Dict[str, Any]) -> str:
    system = (
        _build_system_prompt()
        + "\nRETURN ONLY VALID JSON with keys 'tweet' and 'long'. No code fences. No explanations."
    )
    # Use the same chunked approach as the main summarization if bill has large full_text
    if bill.get("full_text") and len(bill["full_text"]) > 60000:
        logger.info("Using chunked summarization pipeline in repair pass")
        notes = _summarize_full_text_via_chunks(client, bill, bill["full_text"])
        bill_meta_only = dict(bill)
        bill_meta_only.pop("full_text", None)
        user = (
            "Summarize the following bill metadata and extracted notes under the constraints above.\n"
            "Return ONLY a strict JSON object with keys 'tweet' and 'long'.\n"
            f"Bill JSON (metadata only, no full_text):\n{json.dumps(bill_meta_only, ensure_ascii=False)}\n\n"
            f"Extracted notes from full bill text (covering all chunks):\n{notes}"
        )
    else:
        user = _build_user_prompt(bill)
    return _model_call_with_fallback(client, system, user)


def _sanitize_output(obj: Dict[str, Any]) -> Dict[str, str]:
    # Retained for compatibility; no truncation here anymore.
    tweet = str(obj.get("tweet", "")).strip()
    long_s = str(obj.get("long", "")).strip()
    return {"tweet": tweet, "long": long_s}


def _chunk_text(text: str, max_chars: int = 50000, overlap: int = 1000) -> List[str]:
    """
    Split text into overlapping chunks by character count to keep each request modest.
    """
    if max_chars <= 0:
        return [text]
    chunks: List[str] = []
    n = len(text)
    i = 0
    while i < n:
        end = min(n, i + max_chars)
        chunks.append(text[i:end])
        if end >= n:
            break
        i = max(0, end - overlap)
    return chunks


def _summarize_full_text_via_chunks(client: Anthropic, bill: Dict[str, Any], full_text: str) -> str:
    """
    Map-reduce style summarization:
      - Map: summarize each chunk into key factual bullets (plain text).
      - Reduce: concatenate all chunk summaries into a single notes corpus.
    """
    chunks = _chunk_text(full_text, max_chars=50000, overlap=1000)
    logger.info(f"Chunking full_text for map-reduce: total_chars={len(full_text)}; chunks={len(chunks)} (≈50k chars each, 1k overlap)")
    notes_parts: List[str] = []
    # Keep the chunk extractor prompt small and focused
    system = (
        "You extract key factual details from U.S. bill text chunks.\n"
        "- Return ONLY plain text bullet points (no JSON, no code fences).\n"
        "- Focus on: major provisions/programs; agencies involved; funding levels; conditions/restrictions/policy riders; enforcement/penalties; deadlines; authorizations; repeals; appropriations; and definitions."
    )
    bill_meta = {
        "bill_id": bill.get("bill_id"),
        "title": bill.get("title"),
        "latest_action": bill.get("latest_action"),
        "introduced_date": bill.get("introduced_date"),
        "congress": bill.get("congress"),
        "bill_type": bill.get("bill_type"),
        "bill_number": bill.get("bill_number"),
        "text_format": bill.get("text_format"),
        "text_url": bill.get("text_url"),
    }
    for idx, chunk in enumerate(chunks, start=1):
        user = (
            "Extract key factual points from this bill text CHUNK. Be concise but comprehensive for this chunk only.\n"
            "Bill metadata (JSON):\n"
            f"{json.dumps(bill_meta, ensure_ascii=False)}\n\n"
            f"Bill text chunk {idx}/{len(chunks)} (len={len(chunk)} chars):\n{chunk}"
        )
        try:
            logger.info(f"Summarizing chunk {idx}/{len(chunks)} (chars={len(chunk)})...")
            out = _model_call_with_fallback(client, system, user)
            out = (out or "").strip().strip("`")
            logger.info(f"Chunk {idx} summary length: {len(out)} chars")
            notes_parts.append(f"Chunk {idx} notes:\n{out}")
            # Gentle pacing to avoid acceleration limits
            time.sleep(1.0)
        except Exception as e:
            logger.warning(f"Chunk {idx} summarization failed: {e}; continuing with remaining chunks.")
    combined = "\n\n---\n\n".join(notes_parts).strip()
    logger.info(f"Combined notes length from chunks: {len(combined)} chars")
    return combined


def summarize_bill(bill: Dict[str, Any]) -> Dict[str, str]:
    """
    Summarize a bill into tweet and long formats using Claude Sonnet.

    Returns:
        {"tweet": "...", "long": "...", "raw_tweet": "..."}
    """
    start = time.monotonic()
    logger.info("Preparing to summarize bill")

    _ensure_api_key()
    # Create custom http_client to avoid proxy parameter incompatibility
    import httpx
    http_client = httpx.Client()
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], http_client=http_client)

    system = _build_system_prompt()
    # If we have a large full_text, use chunked map-reduce to avoid rate-limit acceleration
    if bill.get("full_text") and len(bill["full_text"]) > 60000:
        logger.info("Using chunked summarization pipeline on full_text (>60k chars)")
        notes = _summarize_full_text_via_chunks(client, bill, bill["full_text"])
        bill_meta_only = dict(bill)
        # Avoid re-sending the entire full_text in the final reduce step
        bill_meta_only.pop("full_text", None)
        user = (
            "Summarize the following bill metadata and extracted notes under the constraints above.\n"
            "Return ONLY a strict JSON object with keys 'tweet' and 'long'.\n"
            f"Bill JSON (metadata only, no full_text):\n{json.dumps(bill_meta_only, ensure_ascii=False)}\n\n"
            f"Extracted notes from full bill text (covering all chunks):\n{notes}"
        )
    else:
        user = _build_user_prompt(bill)
    logger.info(f"Prompt prepared: system={len(system)} chars, user={len(user)} chars")

    # Primary attempt
    try:
        raw = _model_call_with_fallback(client, system, user)
        parsed = _try_parse_json_strict(raw)
    except Exception as e:
        logger.warning(f"Initial parse failed, attempting one repair pass: {e}")
        # Single repair pass
        try:
            raw2 = _repair_pass(client, bill)
            parsed = _try_parse_json_strict(raw2)
        except Exception as e2:
            logger.error(f"Repair pass failed to produce valid JSON: {e2}")
            raise

    # Validate keys
    if not isinstance(parsed, dict):
        raise ValueError("Model did not return a JSON object")

    if "tweet" not in parsed or "long" not in parsed:
        raise ValueError("JSON missing required keys 'tweet' and/or 'long'")

    raw_tweet = str(parsed.get("tweet", "")).strip()
    long_s = str(parsed.get("long", "")).strip()

    # Coherent tightening to ≤200 chars without ellipsis, ending cleanly
    logger.info("Applying coherent tightening to tweet (≤200 chars)...")
    tight_tweet = _coherent_tighten_tweet(client, raw_tweet, bill, limit=200)

    dur = time.monotonic() - start
    logger.info(f"Summarization complete in {dur:.2f}s")
    return {"tweet": tight_tweet, "long": long_s, "raw_tweet": raw_tweet}


def _save_summary(bill_id: str, summary: Dict[str, str], bill: Dict[str, Any]) -> str:
    out_dir = os.path.join("data", "summaries")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{bill_id}.json")
    payload = {
        "bill_id": bill_id,
        "tweet": summary.get("tweet", ""),
        "raw_tweet": summary.get("raw_tweet", ""),
        "long": summary.get("long", ""),
        "source_metadata": {
            "title": bill.get("title"),
            "latest_action": bill.get("latest_action"),
        },
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return out_path


def _select_bills(bills: List[Dict[str, Any]], bill_id: Optional[str], limit: int) -> List[Dict[str, Any]]:
    if bill_id:
        for b in bills:
            if b.get("bill_id") == bill_id:
                return [b]
        return []
    # If no specific bill_id, summarize up to 'limit' returned
    return bills[: max(1, limit)]


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize recent Congress bills with Claude Sonnet.")
    parser.add_argument("--limit", type=int, default=1, help="Number of recent bills to fetch (default: 1)")
    parser.add_argument("--no-save", action="store_true", help="Do not save summaries to disk")
    parser.add_argument("--bill-id", type=str, default=None, help="Optional bill_id to filter on")
    parser.add_argument("--debug", action="store_true", help="Print raw vs. tightened tweet with character counts")
    args = parser.parse_args(argv)

    try:
        logger.info("Loading environment...")
        load_dotenv()  # keep consistent with other modules
        _ensure_api_key()

        from src.fetchers.congress_fetcher import get_recent_bills

        logger.info("Fetching recent bills...")
        t0 = time.monotonic()
        bills = get_recent_bills(limit=max(1, args.limit), include_text=True, text_chars=2000000)
        logger.info("Fetcher called with include_text=True, text_chars=2000000 (no internal truncation)")
        logger.info(f"Fetched {len(bills)} bills in {time.monotonic() - t0:.2f}s")

        selected = _select_bills(bills, args.bill_id, args.limit)
        if not selected:
            logger.error("No matching bill found to summarize")
            return 2

        exit_code = 0
        for bill in selected:
            bid = bill.get("bill_id") or "unknown"
            tf = bill.get("text_format")
            tu = bill.get("text_url")
            ftl = len(bill.get("full_text") or "")
            has_ft = "yes" if ftl > 0 else "no"
            logger.info(f"Summarizing bill {bid}")
            logger.info(f"Bill text metadata: include_text=True; text_format={tf}; text_url={tu}; full_text_attached={has_ft}; full_text_chars={ftl}")
            s0 = time.monotonic()
            summary = summarize_bill(bill)
            logger.info(f"Summary generated in {time.monotonic() - s0:.2f}s")

            if args.debug:
                raw_len = len(summary.get("raw_tweet", "") or "")
                tight_len = len(summary.get("tweet", "") or "")
                print(f"RAW TWEET ({raw_len}/200): {summary.get('raw_tweet','')}")
                print(f"TWEET ({tight_len}/200): {summary.get('tweet','')}")
            else:
                print(f"TWEET: {summary['tweet']}")
            print(f"LONG:  {summary['long']}")

            if not args.no_save and bid != "unknown":
                path = _save_summary(bid, summary, bill)
                logger.info(f"Saved to {path}")

        return exit_code
    except SystemExit:
        raise
    except Exception as e:
        logger.error(f"Failed: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())