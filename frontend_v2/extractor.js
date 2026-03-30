const fs = require('fs');
const path = require('path');

const baseDir = process.cwd();
const outFile = path.join(baseDir, "The_Ultimate_Literal_Codebase.md");
const exts = ['.tsx', '.ts'];
const excludeDirs = ['node_modules', '.git', 'dist', 'build', '.gemini'];

// We do this completely synchronously to avoid missing anything
function walkSync(dir, fileList) {
  const files = fs.readdirSync(dir);
  for (const file of files) {
    const fullPath = path.join(dir, file);
    if (fs.statSync(fullPath).isDirectory()) {
      if (!excludeDirs.includes(file)) {
        walkSync(fullPath, fileList);
      }
    } else {
      if (exts.includes(path.extname(file))) {
        fileList.push(fullPath);
      }
    }
  }
  return fileList;
}

try {
  const allFiles = walkSync(baseDir, []);
  let content = '# The Ultimate Project Codebase\n\n';
  
  for (const file of allFiles) {
    const relPath = path.relative(baseDir, file);
    content += `\n\n## File: ${relPath}\n`;
    content += '```' + (path.extname(file) === '.tsx' ? 'tsx' : 'typescript') + '\n';
    
    const fileContent = fs.readFileSync(file, 'utf8');
    const lines = fileContent.split('\n');
    for (let i = 0; i < lines.length; i++) {
        // Strip out carriage returns if present to avoid mixed line endings in the output
        content += `${i + 1}: ${lines[i].replace(/\r/g, '')}\n`;
    }
    content += '```\n---\n';
  }
  
  fs.writeFileSync(outFile, content, 'utf8');
  console.log(`Successfully wrote ${allFiles.length} files to ${outFile}`);
} catch (e) {
  console.error("Error generating codebase:", e);
}
