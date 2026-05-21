import sys, re

def rtf_to_text(path):
    with open(path, 'rb') as f:
        data = f.read()
    s = data.decode('latin-1')
    out = []
    i = 0
    n = len(s)
    skip_depth = 0           # depth at which we are inside a skipped destination
    depth = 0
    stack_skip = []
    skip_groups = ('pict', 'fonttbl', 'colortbl', 'stylesheet', 'info',
                   'header', 'footer', 'datafield', 'object', 'themedata',
                   'colorschememapping', 'latentstyles', 'datastore',
                   'xmlnstbl', 'rsidtbl', 'generator', 'listtable',
                   'listoverridetable', 'revtbl', 'mmathPr', 'wgrffmtfilter')
    while i < n:
        c = s[i]
        if c == '\\':
            # control word / symbol
            m = re.match(r"\\([a-zA-Z]+)(-?\d+)? ?", s[i:])
            if m:
                cw = m.group(1)
                arg = m.group(2)
                i += m.end()
                if cw == 'u' and arg is not None:
                    code = int(arg)
                    if code < 0:
                        code += 65536
                    if skip_depth == 0:
                        try:
                            out.append(chr(code))
                        except Exception:
                            pass
                    # skip the following uc fallback char
                    if i < n and s[i] not in '\\{}':
                        i += 1
                elif cw in ('par', 'line'):
                    if skip_depth == 0:
                        out.append('\n')
                elif cw in ('tab', 'cell'):
                    if skip_depth == 0:
                        out.append('\t')
                elif cw == 'row':
                    if skip_depth == 0:
                        out.append('\n')
                elif cw in skip_groups and skip_depth == 0:
                    skip_depth = depth
                continue
            else:
                nxt = s[i+1] if i+1 < n else ''
                if nxt == "'":
                    hexs = s[i+2:i+4]
                    i += 4
                    try:
                        b = bytes([int(hexs, 16)])
                        ch = b.decode('cp1256')
                        if skip_depth == 0:
                            out.append(ch)
                    except Exception:
                        pass
                    continue
                elif nxt in ('\\', '{', '}'):
                    if skip_depth == 0:
                        out.append(nxt)
                    i += 2
                    continue
                elif nxt in ('~',):
                    if skip_depth == 0:
                        out.append(' ')
                    i += 2
                    continue
                else:
                    i += 2
                    continue
        elif c == '{':
            depth += 1
            i += 1
        elif c == '}':
            if skip_depth and depth < skip_depth:
                skip_depth = 0
            if skip_depth and depth == skip_depth:
                skip_depth = 0
            depth -= 1
            i += 1
        elif c in '\r\n':
            i += 1
        else:
            if skip_depth == 0:
                out.append(c)
            i += 1
    text = ''.join(out)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    lines = [ln.strip() for ln in text.split('\n')]
    text = '\n'.join(ln for ln in lines if ln)
    return text

if __name__ == '__main__':
    txt = rtf_to_text(sys.argv[1])
    with open(sys.argv[2], 'w', encoding='utf-8') as fo:
        fo.write(txt)
