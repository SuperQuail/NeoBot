// paths.js —— 按路径读写嵌套对象（不可变更新）
export function getPath(target, path) {
  let node = target;
  for (const key of path) {
    if (node == null) return undefined;
    node = node[key];
  }
  return node;
}

export function setPath(target, path, value) {
  if (path.length === 0) return value;
  const clone = structuredClone(target ?? {});
  let node = clone;
  for (const key of path.slice(0, -1)) {
    if (node[key] == null || typeof node[key] !== 'object') node[key] = {};
    node = node[key];
  }
  Object.defineProperty(node, path.at(-1), {
    value,
    writable: true,
    enumerable: true,
    configurable: true,
  });
  return clone;
}

export function joinPath(path) {
  return path.join(' / ');
}

export function matchPath(path, keyword) {
  if (!keyword) return true;
  return joinPath(path).toLowerCase().includes(keyword.toLowerCase());
}
