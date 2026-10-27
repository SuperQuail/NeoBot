/**
 * 本地演示夹具。数据全部虚构，写操作只修改内存，重启后复原。
 * node scripts/preview-api.mjs [--scenario=default|long|empty|readonly]
 * 默认仅监听 127.0.0.1:18881，不连接 NeoBot、模型供应商或插件仓库。
 */
import process from 'node:process';
import console from 'node:console';
import { createPreviewServer } from './preview/server.mjs';
import { DEMO_PASSWORD } from './preview/auth.mjs';
import { DEFAULT_PORT, PREVIEW_HOST } from './preview/http.mjs';

const scenario = process.argv.find((arg) => arg.startsWith('--scenario='))?.split('=')[1] || 'default';
// Port 0 is for temporary contract checks; normal preview remains on 18881.
const portOption = process.argv.find((arg) => arg.startsWith('--port='))?.split('=')[1];
const port = portOption === undefined ? DEFAULT_PORT : Number(portOption);
if (!Number.isInteger(port) || port < 0 || port > 65535) throw new Error('无效的演示端口');
const server = createPreviewServer({ scenario });
server.on('error', (error) => {
  console.error('本地演示夹具启动失败：', error.message);
  process.exitCode = 1;
});
server.listen(port, PREVIEW_HOST, () => {
  console.log('本地演示夹具：http://' + PREVIEW_HOST + ':' + server.address().port + ' · 场景 ' + scenario);
  console.log('演示密码：' + DEMO_PASSWORD + '；所有数据虚构，写入仅在内存，重启复原。');
  console.log('图片只从 dashboard/web/image 固定白名单读取；不会访问真实服务或用户数据。');
});
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => server.close(() => process.exit(0)));
