const fs = require('fs');
const path = require('path');

const outputFile = 'c:\\Users\\asus\\Desktop\\REAL_V6.txt';
const logFile = 'c:\\Users\\asus\\Desktop\\DUMP_LOG_V6.txt';

function log(msg) {
    fs.appendFileSync(logFile, msg + '\n');
    console.log(msg);
}

const excludeDirs = ['node_modules', '.git', 'dist', 'build', '.next', '.vite'];
const extensions = ['.ts', '.tsx', '.css', '.html', '.json', '.js', '.jsx'];

function walkDir(dir, fileList = []) {
  const files = fs.readdirSync(dir);
  files.forEach(file => {
    const filePath = path.join(dir, file);
    const stat = fs.statSync(filePath);
    if (stat.isDirectory()) {
      if (!excludeDirs.includes(file)) {
        walkDir(filePath, fileList);
      }
    } else {
      if (extensions.includes(path.extname(file))) {
        fileList.push(filePath);
      }
    }
  });
  return fileList;
}

try {
    const rootDir = process.cwd();
    log(`Starting consolidation in ${rootDir}...`);
    const files = walkDir(rootDir);
    log(`Found ${files.length} files.`);

    if (fs.existsSync(outputFile)) fs.unlinkSync(outputFile);
    fs.writeFileSync(outputFile, '# THE REAL COMPLETE CODEBASE V6\n');

    files.forEach((file, index) => {
      const relativePath = path.relative(rootDir, file);
      if (relativePath.includes('REAL_V6') || relativePath.includes('DUMP_LOG')) return;
      
      log(`Processing: ${relativePath}`);
      const content = fs.readFileSync(file, 'utf8');
      fs.appendFileSync(outputFile, `\n\n--- FILE: ${relativePath} ---\n`);
      const lines = content.split('\n');
      lines.forEach((line, idx) => {
        fs.appendFileSync(outputFile, `${idx + 1}: ${line}\n`);
      });
    });
    log('DONE SUCCESSFULLY!');
} catch (err) {
    log('ERROR: ' + err.message);
}
