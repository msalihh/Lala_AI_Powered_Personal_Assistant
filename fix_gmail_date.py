import sys
import os

filepath = r"c:\Users\msg\bitirme\backend\app\integrations\gmail.py"
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Add Date to full_text for better LLM reasoning
old_full_text = 'full_text = f"Subject: {subject}\\nFrom: {sender}\\nBody: {clean_body}"'
new_full_text = 'full_text = f"Subject: {subject}\\nFrom: {sender}\\nDate: {date_str}\\nBody: {clean_body}"'
content = content.replace(old_full_text, new_full_text)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

print("Replacement successful")
