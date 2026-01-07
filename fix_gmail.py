import sys
import os

filepath = r"c:\Users\msg\bitirme\backend\app\integrations\gmail.py"
if not os.path.exists(filepath):
    print(f"File not found: {filepath}")
    sys.exit(1)

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace prompt_module usages to make it shared
content = content.replace('prompt_module=prompt_module or "none"  # CRITICAL: Store module for isolation', 'prompt_module="shared"  # Shared across all modules')
content = content.replace('"prompt_module": prompt_module or "none"  # Store module for isolation', '"prompt_module": "shared"  # Shared across all modules')

# Fix existing check in sync_emails (multi-line)
old_existing = """            existing = await db.email_sources.find_one({
                "email_id": msg_id, 
                "user_id": user_id,
                "prompt_module": prompt_module or "none"
            })"""
new_existing = """            existing = await db.email_sources.find_one({
                "email_id": msg_id, 
                "user_id": user_id
            })"""

# Try both double and single quotes for 'none'
content = content.replace(old_existing, new_existing)
content = content.replace(old_existing.replace('"none"', "'none'"), new_existing)

# Fix user_integrations update (multi-line)
old_integ = """                "user_id": user_id, 
                "provider": "gmail",
                "prompt_module": prompt_module or "none"
            },"""
new_integ = """                "user_id": user_id, 
                "provider": "gmail"
            },"""
content = content.replace(old_integ, new_integ)
content = content.replace(old_integ.replace('"none"', "'none'"), new_integ)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

print("Replacement successful")
