const fs = require('fs');
const path = require('path');

const baseDir = '.';
const outputFile = 'Consolidated_Project_Code.md';
const extensions = ['.tsx', '.ts', '.html', '.css', '.json'];
const excludeDirs = ['node_modules', '.git', 'dist', 'build', '.next', '.vite'];
const excludeFiles = ['package-lock.json', outputFile, 'consolidate.js'];

let output = '# Full Project Source Code - Smart Product Search Platform\n\n';
output += 'هذا الملف يحتوي على جميع الأكواد البرمجية للمشروع مع شرح وظيفة كل ملف.\n\n';

function walkDir(dir) {
    const files = fs.readdirSync(dir);
    
    files.forEach(file => {
        const filePath = path.join(dir, file);
        const stat = fs.statSync(filePath);
        
        if (stat.isDirectory()) {
            if (!excludeDirs.includes(file)) {
                walkDir(filePath);
            }
        } else {
            const ext = path.extname(file);
            if (extensions.includes(ext) && !excludeFiles.includes(file)) {
                console.log(`Processing: ${filePath}`);
                const content = fs.readFileSync(filePath, 'utf8');
                const relPath = path.relative(baseDir, filePath);
                
                output += `## File: ${relPath}\n\n`;
                
                let explanation = "الوصف:";
                if (relPath.includes('services')) explanation += " خدمة خلفية (Service) للتعامل مع البيانات.";
                if (relPath.includes('components')) explanation += " مكون واجهة مستخدم (Component).";
                if (relPath.includes('contexts')) explanation += " سياق لإدارة الحالة (Context).";
                if (relPath.includes('types')) explanation += " تعريفات لأنواع البيانات (Types).";
                
                output += `${explanation}\n\n`;
                output += '```' + ext.slice(1) + '\n';
                
                // Add line numbers
                const lines = content.split('\n');
                lines.forEach((line, index) => {
                    output += `${index + 1}: ${line}\n`;
                });
                
                output += '\n```\n\n---\n\n';
            }
        }
    });
}

try {
    walkDir(baseDir);
    fs.writeFileSync(outputFile, output);
    console.log(`Successfully generated ${outputFile}`);
} catch (err) {
    console.error('Error:', err);
}
