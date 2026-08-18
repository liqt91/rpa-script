// run-build.cjs — npm lifecycle shim for rpa-dsh-plugin prepack/build:backend
//
// 为什么需要它：PowerShell 5.1 的 `powershell -File <relative>` 对相对路径解析
// 不可靠（5.1 按自身启动目录而非进程 cwd 解析），而 npm/pnpm 的 lifecycle 脚本
// 由 cmd.exe 执行，cwd 是包目录。node 按本文件位置（__dirname）解析绝对路径后
// 再传给 powershell -File，规避该坑；node 在 npm 环境中必然存在。
//
// 用法：node ../../scripts/run-build.cjs [-BackendOnly]
const { spawnSync } = require('child_process');
const path = require('path');

const script = path.resolve(__dirname, 'build-plugin-package.ps1');
const passthrough = process.argv.slice(2);
const args = ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', script, ...passthrough];

const r = spawnSync('powershell', args, { stdio: 'inherit', shell: false });
if (r.error) {
  console.error('[run-build] failed to spawn powershell:', r.error.message);
  process.exit(1);
}
process.exit(r.status === null ? 1 : r.status);
