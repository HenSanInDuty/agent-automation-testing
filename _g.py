import re

with open('frontend/src/components/pipeline/PrettyOutput.tsx', 'r', encoding='utf-8') as f:
    c = f.read()

# 1: Add FENCE_RE + unwrapValue before TOKEN_RE
FENCE = chr(96) * 3
new_block = f'''
const FENCE_RE = /^{FENCE}(?:json|js|javascript|ts|typescript|text|python)?\\s*\\n([\\s\\S]*?)\\n?{FENCE}\\s*$/;

function unwrapValue(val: unknown, depth = 0): unknown {{
  if (depth > 8) return val;
  if (typeof val === "string") {{
    const trimmed = val.trim();
    const fence = FENCE_RE.exec(trimmed);
    if (fence) {{
      const inner = fence[1].trim();
      try   {{ return unwrapValue(JSON.parse(inner), depth + 1); }}
      catch {{ return unwrapValue(inner, depth + 1); }}
    }}
    if (
      (trimmed.startsWith("{") && trimmed.endsWith("}")) ||
      (trimmed.startsWith("[") && trimmed.endsWith("]"))
    ) {{
      try {{ return unwrapValue(JSON.parse(trimmed), depth + 1); }}
      catch {{ /* keep */ }}
    }}
    return val;
  }}
  if (Array.isArray(val)) return val.map((v) => unwrapValue(v, depth + 1));
  if (val !== null && typeof val === "object")
    return Object.fromEntries(
      Object.entries(val as Record<string, unknown>).map(([k, v]) => [
        k, unwrapValue(v, depth + 1),]));
  return val;
}}
'''

# 2: Fix TOKEN_RE (no capture groups)
new_token_re = 'const TOKEN_RE = /"(?:[^"\\\\]|\\\\.)*"\\s*:|"(?:[^"\\\\]|\\\\.)*"|\\btrue\\b|\\bfalse\\b|\\bnull\\b|-?(?:0|[1-9]\\d*)(?:\\.\\d+)?(?:[eE][+-]?\\d+)?/g;'

# 3: Fix JsonHighlight to use token-based detection
old_highlight_loop = '''    const [full, key, str, bool, nil, num] = match;
    if (key !== undefined) {
      const colon = full.slice(key.length);
      parts.push(
        <span key={match.index}>
          <span className="text-[#7dd3fc]">{key}</span>
          <span className="text-[#8b949e]">{colon}</span>
        </span>,
      );
    } else if (str !== undefined) {
      parts.push(<span key={match.index} className="text-[#a5d6ff]">{str}</span>);
    } else if (bool !== undefined) {
      parts.push(<span key={match.index} className="text-[#79c0ff]">{pool}</span>);
    } else if (nil !== undefined) {
      parts.push(<span key={match.index} className="italic text-[#8b949e]">{nil}</span>);
    } else if (num !== undefined) {
      parts.push(<span key={match.index} className="text-[#ffa657]">{num}</span>);
    } else {
      parts.push(<span key={match.index}>{full}</span>);
    }'''

new_highlight_loop = '''    const tok = m[0];
    if (tok.includes(":") && tok.startsWith('"')) {
      const lastQ = tok.lastIndexOf('"');
      parts.push(
        <span key={m.index}>
          <span className="text-[#7dd3fc]">{tok.slice(0, lastQ + 1)}</span>
          <span className="text-[#8b949e]">{tok.slice(lastQ + 1)}</span>
        </span>,
      );
    } else if (tok.startsWith('"')) {
      parts.push(<span key={m.index} className="text-[#a5d6ff]">{tok}</span>);
    } else if (tok === "true" || tok === "false") {
      parts.push(<span key={m.index} className="text-[#79c0ff]">{tok}</span>);
    } else if (tok === "null") {
      parts.push(<span key={m.index} className="italic text-[#8b949e]">{tok}</span>);
    } else {
      parts.push(<span key={m.index} className="text-[#ffa657]">{tok}</span>);
    }'''

# 4: Fix loop variable match -> m
old_loop = '''  while ((m = TOKEN_RE.exec(src)) !== null) {
    if (m.index > lastIndex)
      parts.push(<span key={"g" + lastIndex} className="text-[#8b949e]">{rsc.slice(lastIndex, m.index)}</span>);'''
new_loop = '''  while ((m = TOKEN_RE.exec(src)) !== null) {
    if (m.index > lastIndex)
      parts.push(<span key={"g" + lastIndex} className="text-[#8b949e]">{rsrc.slice(lastIndex, m.index)}</span>);'''
# Fix rsrc -> src
new_loop = new_loop.replace('rsrc.', 'src.')

# 5: Add unwrapValue call in PrettyOutput
old_parse = '    const parsed: unknown = JSON.parse(value);\n    display = JSON.stringify(parsed, null, 2);'
new_parse = '    const parsed = JSON.parse(value);\n    const unwrapped = unwrapValue(parsed);\n    display = JSON.stringify(unwrapped, null, 2);'

# find where TOKEN_RE is
tokidx = c.find('const TOKEN_RE')
if tokidx < 0:
    print('TOKEN_RE not found!')
else:
    # Add new_block before TOKEN_RE (if not already present)
    if 'unwrapValue' not in c:
        c = c[:tokidx] + new_block + '\n' + c[tokidx:]
        print('added unwrapValue block')
    else:
        print('unwrapValue already present')

# Fix TOKEN_RE
old_token_start = c.find('const TOKEN_RE =')
old_token_end = c.find('/g;', old_token_start) + 4
current_token = c[old_token_start:old_token_end]
if new_token_re not in current_token:
    c = c.replace(current_token, new_token_re)
    print('fixed TOKEN_RE')

# Fix highlight loop
orig_loop = c.find('while ((m = TOKEN_RE')
if orig_loop >= 0:
    c = c.replace(old_loop, new_loop)
    print('fixed loop')

# Fix highlight body
if old_highlight_loop in c:
    c = c.replace(old_highlight_loop, new_highlight_loop)
    print('fixed highlight body')
else:
    print('WARN: highlight body not matched')

# Fix unwrap on parse
if old_parse in c:
    c = c.replace(old_parse, new_parse)
    print('fixed parse call')
else:
    print('WARN: parse block not matched')

with open('frontend/src/components/pipeline/PrettyOutput.tsx', 'w', encoding='utf-8') as f:
    f.write(c)
print('done', len(c))