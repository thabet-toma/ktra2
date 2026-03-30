import traceback

try:
    with open('CODEBASE_FINAL.txt', 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
        
    capture = False
    extracted = []
    for line in lines:
        if '======= ' in line and 'DealManagement.tsx' in line:
            capture = True
        elif '======= ' in line and capture:
            capture = False
            
        if capture:
            extracted.append(line)
            
    with open('deal_frontend.txt', 'w', encoding='utf-8') as f:
        f.writelines(extracted)
        
    print("Done extracting DealManagement.tsx")
except Exception as e:
    with open('deal_error.txt', 'w', encoding='utf-8') as f:
        f.write(traceback.format_exc())
