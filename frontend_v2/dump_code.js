const fs = require('fs');
const path = require('path');
const baseDir = "c:\\Users\\asus\\Desktop\\ثابت\\منصة\\smart-product-search-platform";
const outFile = path.join(baseDir, "Full_Project_Codebase_Literal.md");
const exts = ['.tsx', '.ts'];
const excludeDirs = ['node_modules', '.git', 'dist', 'build', '.gemini'];

let stream = fs.createWriteStream(outFile, { encoding: 'utf8' });
stream.write('# Full Project Codebase (Literal)\n\n');

function walk(dir) {
    let files = fs.readdirSync(dir);
    for (let f of files) {
        let fullPath = path.join(dir, f);
        if (fs.statSync(fullPath).isDirectory()) {
            if (!excludeDirs.includes(f)) {
                walk(fullPath);
            }
        } else {
            if (exts.includes(path.extname(fullPath))) {
                let relPath = path.relative(baseDir, fullPath);
                stream.write(`\n\n## File: ${relPath}\n`);
                stream.write('```' + (path.extname(fullPath) === '.tsx' ? 'tsx' : 'typescript') + '\n');
                let content = fs.readFileSync(fullPath, 'utf8');
                let lines = content.split('\n');
                for (let i = 0; i < lines.length; i++) {
                    stream.write(`${i + 1}: ${lines[i]}\n`);
                }
                stream.write('```\n---\n');
            }
        }
    }
}
try {
    walk(baseDir);
    stream.end();
    console.log("Done successfully!");
} catch (e) {
    console.error(e);
}
