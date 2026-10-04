// Highlight.tsx —— 把文本里命中搜索关键词的片段包成 <mark>
// 搜索面板时用户既想过滤、也想一眼看到「命中在哪」，所以路径与说明都要高亮。
export function Highlight({ text, keyword }: { text: string; keyword?: string }) {
  const value = String(text ?? '');
  const needle = String(keyword || '').trim();
  if (!needle) return <>{value}</>;

  const haystack = value.toLowerCase();
  const target = needle.toLowerCase();
  const parts: Array<{ text: string; hit: boolean }> = [];
  let cursor = 0;
  while (cursor < value.length) {
    const found = haystack.indexOf(target, cursor);
    if (found === -1) {
      parts.push({ text: value.slice(cursor), hit: false });
      break;
    }
    if (found > cursor) parts.push({ text: value.slice(cursor, found), hit: false });
    parts.push({ text: value.slice(found, found + target.length), hit: true });
    cursor = found + target.length;
  }
  return (
    <>
      {parts.map((part, index) =>
        part.hit ? <mark key={index}>{part.text}</mark> : <span key={index}>{part.text}</span>,
      )}
    </>
  );
}

export default Highlight;
