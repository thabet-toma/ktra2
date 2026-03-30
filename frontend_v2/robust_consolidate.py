import os

out_file = 'TOTAL_CODEBASE_V3.md'
excludes = ['node_modules', '.git', 'dist', 'build', '.gemini', '.agent', 'public']
exts = ['.ts', '.tsx', '.css', '.html', '.json']

print("Starting consolidation...")
count = 0

with open(out_file, 'w', encoding='utf-8') as f:
    f.write('# TOTAL PROJECT CODEBASE (LITERAL DUMP)\n\n')
    
    for root, dirs, files in os.walk('.'):
        # Exclude directories
        dirs[:] = [d for d in dirs if d not in excludes]
        
        for file in files:
            if any(file.endswith(ext) for ext in exts):
                if file == out_file or file == 'package-lock.json':
                    continue
                    
                full_path = os.path.join(root, file)
                print(f"Adding: {full_path}")
                count += 1
                
                f.write(f"\n\n---\n## 📄 File: {full_path}\n")
                f.write(f"``` {file.split('.')[-1]}\n")
                
                try:
                    with open(full_path, 'r', encoding='utf-8', errors='ignore') as src:
                        lines = src.readlines()
                        for i, line in enumerate(lines):
                            f.write(f"{i+1:4} | {line}")
                except Exception as e:
                    f.write(f"ERROR READING FILE: {str(e)}\n")
                
                f.write("\n```\n")

print(f"Done! Processed {count} files.")
