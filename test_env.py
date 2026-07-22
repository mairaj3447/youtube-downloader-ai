import os

api_key = os.getenv("OPENAI_API_KEY")
print(f"API Key from environment: {api_key}")

if api_key:
    print("✅ Environment variable is set!")
    print(f"Key starts with: {api_key[:10]}...")
else:
    print("❌ Environment variable is NOT set")