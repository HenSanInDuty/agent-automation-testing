with open('frontend/src/components/pipeline/PrettyOutput.tsx', 'r', encoding='utf-8') as f:
    c = f.read()

old_body = '''    const [full, key, str, bool, nil, num] = match;
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
    }
    lastIndex = TOKEN_RE.lastIndex;'''

new_body = '''    const tok = match[0];
    if (tok.includes(":") && tok.startsWith('"')) {
      const lastQ = tok.lastIndexOf('"');
      parts.push(
        <span key={match.index}>
          <span className="text-[#7dd3fc]">{tok.slice(0, lastQ + 1)}</span>
          <span className="text-[#8b949e]">{tok.slice(lastQ + 1)}</span>
        </span>,
      );
    } else if (tok.startsWith('"')) {
      parts.push(<span key={match.index} className="text-[#a5d6ff]">{tok}</span>);
    } else if (tok === "true" || tok === "false") {
      parts.push(<span key={match.index} className="text-[#79c0ff]">{tok}</span>);
    } else if (tok === "null") {
      parts.push(<span key={match.index} className="italic text-[#8b949e]">{tok}</span>);
    } else {
      parts.push(<span key={match.index} className="text-[#ffa657]">{tok}</span>);
    }
    lastIndex = TOKEN_RE.lastIndex;'''

if old_body in c:
    c = c.replace(old_body, new_body)
    print('fixed JsonHighlight body')
else:
    print('not found - checking around line 52: z')
    # Show what is actually in the file
    lines = c.split('\n')
    for i, l in enumerate(lines[50:70], 51):
        print(i, repr(l))

with open('frontend/src/components/pipeline/PrettyOutput.tsx', 'w', encoding='utf-8') as f:
    f.write(c)
print('done', len(c))