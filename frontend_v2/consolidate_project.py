import os

def generate_consolidated_code():
    base_dir = "."
    output_file = "Full_Project_Code_Summary.md"
    
    # Files to include (source code)
    extensions = ('.tsx', '.ts', '.html', '.css', '.json')
    exclude_dirs = ('node_modules', '.git', 'dist', 'build')
    exclude_files = ('package-lock.json', 'Full_Project_Code_Summary.md')
    
    with open(output_file, 'w', encoding='utf-8') as outfile:
        outfile.write("# مشروع منصة البحث الذكي عن المنتجات - Smart Product Search Platform\n\n")
        outfile.write("هذا الملف يحتوي على جميع الأكواد البرمجية للمشروع مع شرح مختصر لكل ملف ومكوناته.\n\n")
        outfile.write("## فهرس الملفات\n\n")
        
        # Collect files
        all_files = []
        for root, dirs, files in os.walk(base_dir):
            # Exclude directories
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            
            for file in files:
                if file.endswith(extensions) and file not in exclude_files:
                    rel_path = os.path.relpath(os.path.join(root, file), base_dir)
                    all_files.append(rel_path)
        
        # Write Index
        for f in all_files:
            outfile.write(f"- [{f}](#{f.replace('\\', '-').replace('.', '-').lower()})\n")
        
        outfile.write("\n---\n\n")
        
        # Process each file
        for rel_path in all_files:
            print(f"Processing: {rel_path}")
            abs_path = os.path.join(base_dir, rel_path)
            try:
                with open(abs_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                outfile.write(f"## {rel_path}\n\n")
                
                # Simple explanation based on file path/name
                explanation = "شرح:"
                if rel_path.endswith('.tsx'):
                    explanation += " هذا ملف مكون (Component) من واجهة المستخدم (React)."
                elif rel_path.endswith('.ts'):
                    explanation += " هذا ملف برمجية (TypeScript) يحتوي على خدمات أو أنواع بيانات."
                elif rel_path.endswith('.css'):
                    explanation += " هذا ملف تنسيق (CSS) للمظهر."
                elif rel_path.endswith('.json'):
                    explanation += " هذا ملف إعدادات (JSON)."
                
                # Specific explanations for common paths
                if 'services' in rel_path:
                    explanation += " يركز على التواصل مع الخدمات الخارجية مثل Firebase أو معالجة البيانات."
                if 'components' in rel_path:
                    explanation += " يركز على عرض العناصر في الواجهة."
                if 'contexts' in rel_path:
                    explanation += " يركز على إدارة الحالة العامة للتطبيق (State Management)."
                
                outfile.write(f"{explanation}\n\n")
                outfile.write("```" + (rel_path.split('.')[-1] if '.' in rel_path else '') + "\n")
                
                # Add line numbers to the content
                lines = content.splitlines()
                for i, line in enumerate(lines, 1):
                    outfile.write(f"{i}: {line}\n")
                
                outfile.write("\n```\n\n")
                outfile.write("---\n\n")
                
            except Exception as e:
                print(f"Error reading {rel_path}: {str(e)}")
                outfile.write(f"Error reading {rel_path}: {str(e)}\n\n")

    print(f"File generated successfully at: {output_file}")

if __name__ == "__main__":
    generate_consolidated_code()
