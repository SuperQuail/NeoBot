import { Buffer } from 'node:buffer';

export const PREVIEW_HOST = '127.0.0.1';
export const DEFAULT_PORT = 18881;

export const json = (res, value, status = 200) => {
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
    'X-Neobot-Preview': 'fictional-memory-only',
  });
  res.end(JSON.stringify(value));
};
export async function bodyOf(req) {
  let body = '';
  for await (const chunk of req) {
    body += chunk;
    if (Buffer.byteLength(body) > 1024 * 1024) throw new Error('演示请求体过大');
  }
  return body ? JSON.parse(body) : {};
}

export function requiresPost(path) {
  return (
    /\/(?:login|logout|setup|password|validate|reload|preview|save|reset|clear|action|library|assignments|test|provider-models|platform|toggle|update|uninstall|install|proxy|onebot-token|standby|resume|reboot|restart|shutdown|onebot)$/.test(
      path,
    ) || path === '/__preview/scenario'
  );
}
