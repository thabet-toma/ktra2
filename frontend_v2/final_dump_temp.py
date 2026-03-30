import os

# Using common temp path to avoid Arabic character issues in working directory
out_file = os.path.join(os.environ['TEMP'], 'PROJECT_TOTAL_DUMP.md')
log_file = os.path.join(os.environ['TEMP'], 'DUMP_LOG.txt')

excludes = ['node_modules', '.git', 'dist', 'build', '.gemini', '.agent', 'public']
exts = ['.ts', '.tsx', '.css', '.html', '.json']

def log(msg):
    with open(log_file, 'a', encoding='utf-8') as l:
        l.write(msg + '\n')
    print(msg)

if os.path.exists(log_file): os.remove(log_file)
if os.path.exists(out_file): os.remove(out_file)

log(f"Starting Full Consolidation Process to: {out_file}")

try:
    with open(out_file, 'w', encoding='utf-8') as f:
        f.write('# PROJECT TOTAL DUMP (128+ FILES)\n\n')
        
        file_count = 0
        # Use current directory for walking
        for root, dirs, files in os.walk('.'):
            # Prune directories
            dirs[:] = [d for d in dirs if d not in excludes]
            
            for file in files:
                if any(file.endswith(ext) for ext in exts):
                    if file in ['package-lock.json']:
                        continue
                        
                    full_path = os.path.abspath(os.path.join(root, file))
                    log(f"Processing: {full_path}")
                    
                    f.write(f"\n\n---\n## 📄 File: {full_path}\n")
                    f.write(f"``` {file.split('.')[-1]}\n")
                    
                    try:
                        with open(full_path, 'r', encoding='utf-8', errors='ignore') as src:
                            lines = src.readlines()
                            for i, line in enumerate(lines):
                                f.write(f"{i+1:4} | {line}")
                        file_count += 1
                    except Exception as fe:
                        log(f"  ! Error reading {full_path}: {str(fe)}")
                        f.write(f"ERROR READING FILE: {str(fe)}\n")
                    
                    f.write("\n```\n")
                    
        log(f"Successfully processed {file_count} files.")
        
except Exception as e:
    log(f"FATAL ERROR: {str(e)}")

# Try to move it back if possible, but the primary target is the Temp file for safety
log("Process finished.")
