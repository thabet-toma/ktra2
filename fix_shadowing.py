import os
import sys

# Try to find the REAL copy module by temporarily removing the current dir from path
current_dir = os.getcwd()
if current_dir in sys.path:
    sys.path.remove(current_dir)
if '' in sys.path:
    sys.path.remove('')

import copy
real_copy_path = copy.__file__
print(f"Real copy path: {real_copy_path}")

with open(real_copy_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Now overwrite the shadowing file
shadow_file = os.path.join(current_dir, 'copy.py')
with open(shadow_file, 'w', encoding='utf-8') as f:
    f.write(content)

# Also try to rename it one last time just in case it works now
try:
    os.rename(shadow_file, os.path.join(current_dir, 'copy_restored_final.py'))
    print("SUCCESS: Renamed copy.py to copy_restored_final.py")
except Exception as e:
    print(f"FAILED to rename: {e}")
    print("Shadowing file was overwritten with real copy.py content instead.")
