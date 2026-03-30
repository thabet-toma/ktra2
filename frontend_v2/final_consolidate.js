const fs = require('fs');
const path = require('path');

const outFile = 'THE_ULTIMATE_CODEBASE.md';
const baseDir = '.';
const excludes = ['node_modules', '.git', 'dist', 'build', '.gemini', '.agent'];
const extensions = ['.ts', '.tsx', '.css', '.html', '.json'];

// Clear/Create file
fs.writeFileSync(outFile, '# THE ULTIMATE PROJECT CODEBASE (LITERAL DUMP)\n\n');
fs.appendFileSync(outFile, '> This file contains the complete source code of the project, line by line, as requested.\n\n---\n');

function walk(dir) {
    const files = fs.readdirSync(dir);
    for (const file of files) {
        const fullPath = path.join(dir, file);
        const stats = fs.statSync(fullPath);

        if (stats.isDirectory()) {
            if (!excludes.includes(file)) {
                walk(fullPath);
            }
        } else {
            const ext = path.extname(file);
            if (extensions.includes(ext) && !file.includes('package-lock.json') && !file.includes(outFile)) {
                console.log(`Processing: ${fullPath}`);
                const relativePath = path.relative(baseDir, fullPath);
                const content = fs.readFileSync(fullPath, 'utf8');
                const lines = content.split('\n');
                
                let fileHeader = `\n\n## 📄 File: ${relativePath}\n`;
                fileHeader += `**Path:** \`${fullPath}\`  \n`;
                fileHeader += `**Extension:** \`${ext}\`  \n`;
                fileHeader += `**Lines:** ${lines.length}\n\n`;
                fileHeader += '```' + (ext.slice(1) || 'text') + '\n';
                
                fs.appendFileSync(outFile, fileHeader);
                
                // Writing in chunks to avoid memory issues with very large files
                const chunkedLines = [];
                for (let i = 0; i < lines.length; i++) {
                    chunkedLines.push(`${(i + 1).toString().padStart(4, ' ')} | ${lines[i]}`);
                    if (chunkedLines.length > 500) {
                        fs.appendFileSync(outFile, chunkedLines.join('\n') + '\n');
                        chunkedLines.length = 0;
                    }
                }
                if (chunkedLines.length > 0) {
                    fs.appendFileSync(outFile, chunkedLines.join('\n') + '\n');
                }
                
                fs.appendFileSync(outFile, '```\n\n---\n');
            }
        }
    }
}

try {
    walk(baseDir);
    console.log(`\n✅ Done! Entire codebase dumped into: ${outFile}`);
} catch (err) {
    console.error(`\n❌ Error during consolidation:`, err);
}
