import { useState, useRef, useEffect, useCallback } from 'react';
import { api } from '../api';

/**
 * 图像元素上传弹窗：注册参考图供「图像查找 / 图像点击」指令下拉引用。
 * 三种获取方式：
 *   1. 📷 现场截图 — 启动系统截图工具（SnippingTool），框选完自动回填（后端轮询剪贴板）
 *   2. Ctrl+V 直接粘贴 — Win+Shift+S 截到剪贴板后，在弹窗内粘贴即可
 *   3. 选择文件 — 已保存的截图兜底
 */
export default function UploadImageModal({ wfId, onClose, onSaved }) {
  const [name, setName] = useState('');
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState('');
  const [similarity, setSimilarity] = useState(0.8);
  const [scope, setScope] = useState('screen');
  const [uploading, setUploading] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [error, setError] = useState('');
  const fileRef = useRef(null);
  const pollTimer = useRef(null);
  const baselineRef = useRef('');
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  const applyImage = useCallback((dataUrl, label = '') => {
    // dataUrl → File（上传走 multipart）
    const mime = dataUrl.split(',')[0].match(/data:(.*?);/)?.[1] || 'image/png';
    const b64 = dataUrl.split(',')[1] || '';
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const f = new File([bytes], label || `screenshot-${Date.now()}.png`, { type: mime });
    setFile(f);
    setPreview(dataUrl);
  }, []);

  // 现场截图：启动工具 → 轮询剪贴板 → 自动回填
  const startCapture = async () => {
    if (capturing) return;
    setCapturing(true);
    setError('');
    try {
      const d = await api.screenshotStart();
      baselineRef.current = d.baseline || '';
      const startedAt = Date.now();
      const tick = async () => {
        try {
          const r = await api.screenshotPoll(baselineRef.current);
          if (r.ready && r.dataUrl) {
            applyImage(r.dataUrl, `capture-${Date.now()}.png`);
            setCapturing(false);
            return;
          }
        } catch {}
        if (Date.now() - startedAt > 90000) { // 90s 超时
          setCapturing(false);
          setError('未检测到截图，请确认已框选完成，或改用粘贴/选择文件');
          return;
        }
        pollTimer.current = setTimeout(tick, 500);
      };
      tick();
    } catch (e) {
      setCapturing(false);
      setError(e.message || '无法启动截图工具');
    }
  };

  // 粘贴：Win+Shift+S 截到剪贴板后 Ctrl+V 直接填入
  useEffect(() => {
    const onPaste = (e) => {
      if (capturing) return; // 截图流程中不抢
      const items = e.clipboardData?.items || [];
      for (const item of items) {
        if (item.type?.startsWith('image/')) {
          const blob = item.getAsFile();
          if (blob) {
            const reader = new FileReader();
            reader.onload = () => applyImage(reader.result, 'pasted.png');
            reader.readAsDataURL(blob);
            return;
          }
        }
      }
    };
    window.addEventListener('paste', onPaste);
    return () => {
      window.removeEventListener('paste', onPaste);
      if (pollTimer.current) clearTimeout(pollTimer.current);
    };
  }, [capturing, applyImage]);

  // 关闭时清理轮询
  useEffect(() => () => {
    if (pollTimer.current) clearTimeout(pollTimer.current);
  }, []);

  function pickFile(f) {
    setFile(f);
    if (f) {
      const reader = new FileReader();
      reader.onload = () => setPreview(reader.result);
      reader.readAsDataURL(f);
    } else {
      setPreview('');
    }
  }

  async function submit() {
    const trimmed = name.trim();
    if (!trimmed) { setError('请输入元素名'); return; }
    if (!file) { setError('请先截图/粘贴/选择参考图'); return; }
    setError('');
    setUploading(true);
    try {
      await api.uploadImageElement(wfId, trimmed, file, { similarity, scope });
      if (onSaved) onSaved();
      onCloseRef.current();
    } catch (e) {
      setError(e.message || '上传失败');
    } finally {
      setUploading(false);
    }
  }

  const inputClass = "w-full px-3 py-2 bg-surface-2 border border-border-strong rounded text-sm text-body outline-none focus:border-accent";
  const actionBtn = "flex-1 flex flex-col items-center gap-1.5 px-3 py-4 rounded-lg border transition-colors text-xs";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={(e) => { if (e.target === e.currentTarget && !capturing) onClose(); }}>
      <div className="bg-surface rounded-lg shadow-xl p-6 w-[520px] max-h-[92vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-medium text-inverse flex items-center gap-2">
            <i className="fas fa-image text-vision"></i>
            上传图像元素
          </h3>
          <button onClick={() => { if (!capturing) onClose(); }} className="text-faint hover:text-muted" title="关闭">
            <i className="fas fa-times"></i>
          </button>
        </div>

        <div className="space-y-4">
          {/* 三种获取方式 */}
          <div>
            <div className="text-xs text-muted mb-2">参考图获取方式</div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={startCapture}
                disabled={capturing}
                className={`${actionBtn} ${capturing
                  ? 'bg-vision-soft border-vision text-vision'
                  : 'bg-vision-soft hover:bg-vision-soft border-vision text-vision'}`}
                title="打开系统截图工具，框选区域，完成后自动回填"
              >
                {capturing
                  ? <><i className="fas fa-spinner fa-spin text-sm"></i><span>等待框选…</span></>
                  : <><i className="fas fa-camera text-sm"></i><span>现场截图</span></>}
              </button>
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                className={`${actionBtn} bg-accent-soft hover:bg-accent-soft border-blue-200 text-accent`}
                title="选择已保存的截图文件"
              >
                <i className="fas fa-folder-open text-sm"></i>
                <span>选择文件</span>
              </button>
              <input
                ref={fileRef}
                type="file"
                accept="image/png,image/jpeg,image/webp,image/bmp"
                className="hidden"
                onChange={(e) => pickFile(e.target.files?.[0] || null)}
              />
            </div>
            <div className="mt-2 flex items-center gap-1.5 text-[11px] text-faint">
              <i className="fas fa-keyboard"></i>
              <span>也可以用 Win+Shift+S 截图后，在弹窗内直接 <b className="text-muted">Ctrl+V</b> 粘贴</span>
            </div>
            {capturing && (
              <div className="mt-2 text-[11px] text-vision bg-vision-soft px-2 py-1.5 rounded flex items-center gap-1.5">
                <i className="fas fa-camera"></i>
                已打开系统截图工具：框选目标区域，完成后自动回填…
              </div>
            )}
          </div>

          {/* 预览 */}
          {preview && (
            <div className="flex items-start gap-3">
              <img src={preview} alt="预览" className="max-h-40 border border-border rounded bg-surface" />
              <div className="flex flex-col gap-1.5">
                <span className="text-[10px] text-faint">已就绪{file ? `：${file.name}` : ''}</span>
                <button
                  type="button"
                  onClick={() => { setFile(null); setPreview(''); }}
                  className="text-[11px] text-danger hover:underline text-left"
                >
                  清除重选
                </button>
              </div>
            </div>
          )}

          {/* 元素名 */}
          <div>
            <div className="text-xs text-muted mb-1.5">元素名（findImage/clickImage 下拉引用）</div>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className={inputClass}
              placeholder="如：确认按钮 / login_btn"
              onKeyDown={(e) => { if (e.key === 'Enter') submit(); }}
            />
            <div className="text-[10px] text-faint mt-1">建议短名；同名图像元素会覆盖更新，同名非图像元素会被拒绝。</div>
          </div>

          {/* 匹配参数 */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="text-xs text-muted mb-1.5">默认相似度阈值</div>
              <input
                type="number"
                min={0.6}
                max={1.0}
                step={0.05}
                value={similarity}
                onChange={(e) => setSimilarity(Number(e.target.value))}
                className={inputClass}
              />
            </div>
            <div>
              <div className="text-xs text-muted mb-1.5">默认匹配范围</div>
              <select value={scope} onChange={(e) => setScope(e.target.value)} className={inputClass}>
                <option value="screen">全屏幕（默认）</option>
                <option value="page">浏览器页面内容</option>
              </select>
            </div>
          </div>

          {error && <div className="text-xs text-danger bg-danger-soft px-2 py-1.5 rounded">{error}</div>}

          <div className="flex justify-end gap-2">
            <button
              onClick={onClose}
              className="px-4 py-1.5 text-xs text-muted hover:bg-surface-3 rounded border border-border"
              disabled={uploading || capturing}
            >
              取消
            </button>
            <button
              onClick={submit}
              disabled={uploading || capturing || !file}
              className="px-4 py-1.5 text-xs text-white bg-vision hover:bg-vision rounded disabled:opacity-50 flex items-center gap-1.5"
            >
              {uploading && <i className="fas fa-spinner fa-spin"></i>}
              {uploading ? '上传中…' : '注册为图像元素'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
