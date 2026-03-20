import os
import sys
from app.core.security import get_password_hash

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# --- Configuration ---
ADMIN_PASSWORD = "adminpassword123"

# --- Hash Generation ---
try:
    hashed_password = get_password_hash(ADMIN_PASSWORD)
    print("\n---------------------------------------------------------")
    print(f"HASH GENERATED SUCCESSFULLY for password: '{ADMIN_PASSWORD}'")
    print("---------------------------------------------------------")
    print(f"HASHED:")
    print(hashed_password)
    print("---------------------------------------------------------\n")

except Exception as e:
    print(f"\n ERROR during hash generation: {e}")
