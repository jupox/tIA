from supabase import create_client, Client
import os

# It's better to ensure rxconfig is importable or pass vars.
# For worker context, direct env var reading is often more straightforward.
SUPABASE_URL = os.getenv("SUPABASE_URL", "YOUR_SUPABASE_URL_HERE")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY", "YOUR_SUPABASE_KEY_HERE")

def get_supabase_client() -> Client:
    # Ensure that SUPABASE_URL and SUPABASE_KEY are not the placeholder values
    if SUPABASE_URL == "YOUR_SUPABASE_URL_HERE" or SUPABASE_KEY == "YOUR_SUPABASE_KEY_HERE":
        raise ValueError("Supabase URL or Key is not configured. Please set the environment variables.")
    return create_client(SUPABASE_URL, SUPABASE_KEY)
