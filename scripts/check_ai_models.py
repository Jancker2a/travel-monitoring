#!/usr/bin/env python3
"""
Utility script to check and display accessible AI models for your OpenAI and Gemini API keys.
Queries:
- GET https://api.openai.com/v1/models
- GET https://generativelanguage.googleapis.com/v1beta/models?key=...
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error


def check_openai(api_key: str):
    print("=" * 70)
    print("🤖 Checking OpenAI API Key...")
    print("=" * 70)
    url = "https://api.openai.com/v1/models"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "TravelPriceMonitor/1.0",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = sorted([m["id"] for m in data.get("data", []) if "id" in m])
            print(f"✓ Total models accessible: {len(models)}\n")
            
            chat_models = [m for m in models if any(m.startswith(p) for p in ("gpt-", "o1", "o3", "chatgpt"))]
            print(f"💬 Chat & Reasoning Models ({len(chat_models)}):")
            for m in chat_models:
                print(f"   • {m}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:200]
        print(f"❌ OpenAI HTTP Error {e.code}: {body}")
    except Exception as e:
        print(f"❌ Error querying OpenAI API: {e}")


def check_gemini(api_key: str):
    print("\n" + "=" * 70)
    print("✨ Checking Google Gemini API Key...")
    print("=" * 70)
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    req = urllib.request.Request(
        url,
        headers={"Content-Type": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("name", "").replace("models/", "") for m in data.get("models", [])]
            print(f"✓ Total Gemini models accessible: {len(models)}\n")
            
            flash_and_pro = [m for m in models if "gemini" in m]
            print(f"✨ Gemini Models ({len(flash_and_pro)}):")
            for m in sorted(flash_and_pro):
                print(f"   • {m}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:200]
        print(f"❌ Gemini HTTP Error {e.code}: {body}")
    except Exception as e:
        print(f"❌ Error querying Gemini API: {e}")


def main():
    parser = argparse.ArgumentParser(description="Query and display accessible models for OpenAI / Gemini keys.")
    parser.add_argument("--openai-key", default=os.getenv("OPENAI_API_KEY"), help="OpenAI API Key (or env OPENAI_API_KEY)")
    parser.add_argument("--gemini-key", default=os.getenv("GEMINI_API_KEY"), help="Google Gemini API Key (or env GEMINI_API_KEY)")
    args = parser.parse_args()

    if not args.openai_key and not args.gemini_key:
        print("ℹ️  No API keys provided in arguments or environment variables.")
        print("Usage:")
        print("  python scripts/check_ai_models.py --openai-key 'sk-...'")
        print("  python scripts/check_ai_models.py --gemini-key 'AIzaSy...'")
        print("  OPENAI_API_KEY='sk-...' python scripts/check_ai_models.py")
        sys.exit(0)

    if args.openai_key:
        check_openai(args.openai_key)
    if args.gemini_key:
        check_gemini(args.gemini_key)


if __name__ == "__main__":
    main()
