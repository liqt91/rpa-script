/**
 * getText — DOM handler.
 *
 * Self-contained text extraction. Future extraction commands (getValue /
 * getAttribute / ...) will each own their own handler.
 */
registerHandler('getText', async function getText({ locator, selectorFamily, extra }) {
  const el = findTarget(locator, selectorFamily, extra);
  // 表单元素（input/textarea/select）的文本在 value 属性里，textContent 恒为空；
  // 回退读 value 使「输入后回读验证」（getText + ifVarEquals）对输入框可用。
  const isForm = /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName || '');
  const value = (isForm ? (el.value ?? '') : (el.textContent || el.innerText || '')).trim();
  return { value, text: value, extracted: value };
});
