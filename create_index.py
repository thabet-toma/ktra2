import re

file_path = r'C:\Users\asus\Desktop\ktra\CODEBASE_FINAL.txt'
index_path = r'C:\Users\asus\Desktop\ktra\codebase_index.txt'

pattern = re.compile(r'^======= (.*) =======$', re.MULTILINE)

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
        matches = pattern.finditer(content)
        with open(index_path, 'w', encoding='utf-8') as out:
            for match in matches:
                # Calculate line number (this is slow for large files but needed once)
                line_no = content.count('\n', 0, match.start()) + 1
                out.write(f"Line {line_no}: {match.group(1)}\n")
    print(f"Index created at {index_path}")
except Exception as e:
    print(f"Error: {e}")
