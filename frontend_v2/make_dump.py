import os, pathlib

root = os.getcwd()
out  = r'c:\Users\asus\Desktop\CODEBASE_FINAL.txt'
skip = {'node_modules','.git','dist','build'}
exts = {'.ts','.tsx','.css','.html','.js','.jsx','.json'}

total = 0
with open(out,'w',encoding='utf-8') as f:
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in skip]
        for fn in files:
            if pathlib.Path(fn).suffix in exts:
                full = os.path.join(dirpath, fn)
                rel  = os.path.relpath(full, root)
                f.write(f'\n\n======= {rel} =======\n')
                try:
                    lines = open(full,encoding='utf-8',errors='ignore').readlines()
                    for i,line in enumerate(lines,1):
                        f.write(f'{i}: {line}')
                    total += len(lines)
                except Exception as e:
                    f.write(f'ERROR: {e}\n')

print(f'DONE! Total lines: {total}')
print(f'File saved at: {out}')
