import traceback
try:
    with open('CODEBASE_FINAL.txt', 'rb') as f:
        content = f.read()
    if b'\x00' in content:
        text = content.decode('utf-16', errors='replace')
    else:
        text = content.decode('utf-8', errors='replace')
    with open('CODEBASE_UTF8.txt', 'w', encoding='utf-8') as f:
        f.write(text)
    print('Converted successfully')
except Exception as e:
    traceback.print_exc()
