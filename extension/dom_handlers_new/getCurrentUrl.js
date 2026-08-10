// ─── getCurrentUrl ──────────────────────────────────────────────
// 后端 ifUrlContains / whileCondition(urlContains) 的查询入口。

registerHandler('getCurrentUrl', async function getCurrentUrlHandler() {
    return { url: location.href, title: document.title };
});
