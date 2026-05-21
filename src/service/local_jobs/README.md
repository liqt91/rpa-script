# local_jobs/ — 本地开发脚本隔离目录

此目录用于本地开发和调试脚本，**不会被 `client.py update` 覆盖**，也**不会被服务端扫描**。

## 使用方式

1. 在 `local_jobs/<name>/` 下创建你的脚本：
   ```
   local_jobs/
     my_scraper/
       main.py      # 必须包含 run(url, **params) -> dict
       job.yaml     # 可选，声明参数和 AI 能力
   ```

2. 本地运行测试：
   ```bash
   python client.py run my_scraper <url>
   ```
   `client.py` 会优先从 `local_jobs/` 加载脚本。

3. 开发完成后，将整个目录拷贝到 `jobs/<name>/` 并提交到 git：
   ```bash
   cp -r local_jobs/my_scraper jobs/
   git add jobs/my_scraper
   git commit -m "add my_scraper script"
   ```

## 与 jobs/ 的区别

| 目录 | 用途 | 被 update 覆盖 | 被服务端扫描 |
|------|------|---------------|-------------|
| `jobs/` | 已发布脚本 | 是 | 是 |
| `local_jobs/` | 开发中脚本 | **否** | **否** |

## 注意事项

- `local_jobs/` 下的内容默认不被 git 跟踪（见 `.gitignore`）
- 脚本内可以正常 `import shared.xxx` 和 `from shared.ai_bridge import invoke`
