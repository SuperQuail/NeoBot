// paths.ts —— 按路径读写嵌套对象（不可变更新）

export type PathKey = string | number;
export type Path = readonly PathKey[];
export type AnyRecord = Record<string, any>;

function arrayIndex(node: unknown, key: PathKey, create = false): PathKey {
  if (!Array.isArray(node) || typeof key !== 'number') return key;
  if (create && key < 0) {
    while (node.length < -key) node.unshift({});
  }
  const index = key < 0 ? node.length + key : key;
  if (create) {
    // 序列输入别名需要可 JSON/TOML 持久化的中间槽，不能留下 undefined 洞。
    while (node.length <= index) node.push({});
  }
  return index;
}

/** 读取嵌套值；任一层为 null/undefined 时返回 undefined */
export function getPath(target: unknown, path: Path): any {
  let node: any = target;
  for (const key of path) {
    if (node == null) return undefined;
    node = node[arrayIndex(node, key)];
  }
  return node;
}

/** 不可变写入：返回克隆后的新对象 */
export function setPath<T>(target: T, path: Path, value: unknown): T {
  if (path.length === 0) return value as T;
  const clone = structuredClone(target ?? ({} as T)) as AnyRecord;
  let node: AnyRecord = clone;
  for (const [index, part] of path.slice(0, -1).entries()) {
    const key = arrayIndex(node, part, true);
    const next = node[key];
    if (next == null || typeof next !== 'object')
      node[key as PathKey] = typeof path[index + 1] === 'number' ? [] : {};
    node = node[key as PathKey];
  }
  Object.defineProperty(node, arrayIndex(node, path[path.length - 1], true), {
    value,
    writable: true,
    enumerable: true,
    configurable: true,
  });
  return clone as T;
}

export function joinPath(path: Path): string {
  return path.join(' / ');
}

export function matchPath(path: Path, keyword?: string): boolean {
  if (!keyword) return true;
  return joinPath(path).toLowerCase().includes(keyword.toLowerCase());
}
