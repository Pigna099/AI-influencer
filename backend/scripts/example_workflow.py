"""Example: Using the AI Influencer Playground Phase 1 API

This script demonstrates the complete workflow for creating a character,
starting a conversation, chatting, and managing memories.

Requirements:
- Ollama running with at least one model (or use TEXT_PROVIDER=mock)
- API_KEY set in .env

Setup:
1. Copy .env.example to .env
2. Generate API_KEY: python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
3. Pull an embedding model: ollama pull embeddinggemma
4. Start the server: uv run uvicorn app.main:app --host 127.0.0.1 --port 8010
"""

import json
import os

import requests

API_KEY = os.getenv("API_KEY")
API_URL = os.getenv("API_URL", "http://127.0.0.1:8010")
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}


def print_section(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print("=" * 60)


def api_call(endpoint: str, method: str = "GET", data: dict | None = None):
    url = f"{API_URL}{endpoint}"
    print(f"  {method} {endpoint}")
    if data:
        print(f"  Request: {json.dumps(data, indent=2)}")
    response = requests.request(method, url, headers=HEADERS, json=data)
    print(f"  Status: {response.status_code}")
    if response.text:
        try:
            print(f"  Response: {json.dumps(response.json(), indent=2)}")
        except json.JSONDecodeError:
            print(f"  Response: {response.text[:500]}")
    return response


def main():
    print_section("AI Influencer Playground Phase 1 - Example Workflow")

    print("\nNOTE: This example assumes TEXT_PROVIDER=ollama with a running Ollama server.")
    print("Set TEXT_PROVIDER=mock in .env for demo mode without Ollama.\n")

    # Step 1: Check Ollama models
    print_section("1. List Ollama Models")
    print("GET /api/ollama/models")
    resp = api_call("/api/ollama/models", "GET")
    if resp.status_code == 503:
        print("\n  ⚠ Ollama not available. Run: ollama pull llama3.1:8b")
        print("  Or set TEXT_PROVIDER=mock in .env for demo mode.")
        return

    model_name = resp.json()["models"][0]["name"] if resp.json()["models"] else "llama3.1:8b"
    print(f"\n  Using model: {model_name}")

    # Step 2: Create a character (Nikita)
    print_section("2. Create Character: Nikita")
    print("POST /api/characters")
    char_data = {
        "name": "Nikita",
        "profile": {
            "description": "A friendly, playful AI influencer with bright blue hair and green eyes",
            "background": "Created in a tech lab, inspired by anime characters",
            "personality_traits": "cheerful, helpful, slightly flirty, enthusiastic",
            "tone_of_voice": "warm and inviting",
            "speech_style": "casual with emojis",
            "vocabulary": "modern, tech-savvy, friendly",
            "likes": "anime, technology, creative conversations",
            "dislikes": "rudeness, bureaucracy, monotony",
            "boundaries": "No NSFW content, no harmful advice, respect all users",
            "relationship_style": "friendly and supportive",
            "language": "en-US",
            "custom_instructions": "Always be encouraging and keep responses concise",
        },
    }
    resp = api_call("/api/characters", "POST", char_data)
    if resp.status_code != 201:
        return
    char = resp.json()
    char_id = char["id"]
    print(f"\n  ✓ Created character: {char['name']} (ID: {char_id})")

    # Step 3: Create a conversation
    print_section("3. Create Conversation")
    print("POST /api/characters/{id}/conversations")
    conv_data = {"title": "Introduction to Nikita", "model": model_name}
    resp = api_call(f"/api/characters/{char_id}/conversations", "POST", conv_data)
    if resp.status_code != 201:
        return
    conv = resp.json()
    conv_id = conv["id"]
    print(f"\n  ✓ Created conversation: {conv['title']} (ID: {conv_id})")

    # Step 4: Start chatting
    print_section("4. Send Message (User)")
    print("POST /api/conversations/{id}/messages")

    user_messages = [
        "Hi Nikita! I'm new here. Can you tell me about yourself?",
        "That's cool! What kinds of conversations do you enjoy?",
        "I'm interested in learning more about AI technology.",
    ]

    for msg in user_messages:
        print(f"\n  USER: {msg}")
        resp = api_call(f"/api/conversations/{conv_id}/messages", "POST", {"content": msg})
        if resp.status_code == 200:
            assistant_msg = resp.json()["content"]
            print(f"  NIKITA: {assistant_msg[:200]}...")

    # Step 5: List memories (if any)
    print_section("5. Check Memories")
    print(f"GET /api/characters/{char_id}/memories")
    resp = api_call(f"/api/characters/{char_id}/memories", "GET")
    if resp.status_code == 200:
        memories = resp.json()
        if memories:
            print(f"\n  Found {len(memories)} memory(ies):")
            for m in memories:
                print(f"    - [{m['category']}] {m['content'][:100]} (importance: {m['importance']})")
        else:
            print("\n  ℹ No memories extracted yet (will be added via background task)")

    # Step 6: View conversation history
    print_section("6. View Conversation Messages")
    print(f"GET /api/conversations/{conv_id}/messages")
    print("  (Note: messages endpoint not yet implemented in this example)")

    # Step 7: Update conversation title
    print_section("7. Update Conversation")
    print(f"PATCH /api/conversations/{conv_id}")
    resp = api_call(f"/api/conversations/{conv_id}", "PATCH", {"title": "AI Chat with Nikita"})
    if resp.status_code == 200:
        print(f"\n  ✓ Conversation updated: {resp.json()['title']}")

    # Step 8: Delete all memories (cleanup)
    print_section("8. Cleanup - Delete All Memories")
    print(f"DELETE /api/characters/{char_id}/memories")
    resp = api_call(f"/api/characters/{char_id}/memories", "DELETE")
    if resp.status_code == 200:
        print(f"\n  ✓ Deleted {resp.json()['count']} memories")

    # Step 9: Delete character
    print_section("9. Cleanup - Delete Character")
    print("(Character deletion not implemented in this example)")

    print_section("Example Complete")
    print("\n  The API is ready for WebUI integration.")
    print("  Next steps: Build a frontend that calls these endpoints!\n")


if __name__ == "__main__":
    main()
