import os

def generate_full_codebase_dump():
    base_dir = os.path.abspath(".")
    output_file = "THE_COMPLETE_LITERAL_CODEBASE_FINAL.md"
    
    # Files to include (source code)
    extensions = ('.tsx', '.ts', '.html', '.css', '.json')
    exclude_dirs = ('node_modules', '.git', 'dist', 'build', '.gemini', '.agent', '.dart_tool')
    exclude_files = ('package-lock.json', output_file, 'PROJECT_TOTAL_DUMP.md', 'THE_ULTIMATE_CODEBASE.md', 'LITERAL_COMPLETE_CODEBASE_V5.md')
    
    print(f"Starting complete dump to {output_file}...")
    
    with open(output_file, 'w', encoding='utf-8') as outfile:
        outfile.write("# THE COMPLETE LITERAL CODEBASE - FINAL COMPREHENSIVE DUMP\n")
        outfile.write(f"## PROJECT: Smart Product Search Platform\n")
        outfile.write(f"## GENERATED ON: 2026-03-25\n\n")
        outfile.write("> [!IMPORTANT]\n")
        outfile.write("> This file contains the ABSOLUTE, LINE-BY-LINE source code for the entire project.\n")
        outfile.write("> To find a specific file, please search for '## File: [filename]'.\n\n")
        outfile.write("---\n")
        
        file_count = 0
        total_lines = 0
        
        for root, dirs, files in os.walk(base_dir):
            # Exclude directories
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            
            for file in files:
                if file.endswith(extensions) and file not in exclude_files:
                    rel_path = os.path.relpath(os.path.join(root, file), base_dir)
                    abs_path = os.path.join(root, file)
                    
                    print(f"Adding: {rel_path}")
                    
                    outfile.write(f"\n\n---\n## File: {rel_path}\n")
                    outfile.write(f"**Full Path:** `{abs_path}`\n\n")
                    
                    ext = file.split('.')[-1]
                    outfile.write(f"```{ext}\n")
                    
                    try:
                        with open(abs_path, 'r', encoding='utf-8', errors='ignore') as src:
                            lines = src.readlines()
                            for i, line in enumerate(lines, 1):
                                # Ensure the line ends with a newline, avoid extra ones
                                formatted_line = line if line.endswith('\n') else line + '\n'
                                outfile.write(f"{i:4} | {formatted_line}")
                            
                            file_count += 1
                            total_lines += len(lines)
                    except Exception as e:
                        print(f"  FAILED to read {rel_path}: {e}")
                        outfile.write(f"ERROR READING FILE CONTENT: {str(e)}\n")
                    
                    outfile.write("```\n")
        
        outfile.write(f"\n\n---\n# END OF DUMP\n")
        outfile.write(f"### SUMMARY\n")
        outfile.write(f"- Total Files processed: {file_count}\n")
        outfile.write(f"- Total Lines documented: {total_lines}\n")

    print(f"\n✅ SUCCESS! Documented {file_count} files and {total_lines} lines.")
    print(f"Output saved to: {output_file}")

if __name__ == "__main__":
    generate_full_codebase_dump()
