import shutil
import traceback
import os

src = r"C:\Users\asus\Desktop\ثابت\منصة\smart-product-search-platform"
dst = r"C:\Users\asus\Desktop\ktra\frontend_v2"

print(f"Starting copy from {src} to {dst}")
try:
    shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns('node_modules', '.git', '.vercel', 'dist', 'build'))
    print("Copy successful")
except Exception as e:
    print(f"Error copying files: {e}")
    traceback.print_exc()
