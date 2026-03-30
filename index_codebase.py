import re

file_path = r'C:\Users\asus\Desktop\ktra\CODEBASE_FINAL.txt'
headers = []

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f, 1):
            if line.startswith('=======') and line.strip().endswith('======='):
                headers.append(f"{i}: {line.strip()}")
                if len(headers) > 500: # Safety cap
                    break
except Exception as e:
    print(f"Error: {e}")

with open(r'C:\Users\asus\Desktop\ktra\file_index.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(headers))

print(f"Found {len(headers)} headers.")
