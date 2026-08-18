import { useState, useEffect, useCallback } from 'react';

/**
 * 图片灯箱 — 全屏预览捕获截图
 * 背景模糊压暗 + 淡入缩放动画；Esc / 点背景 / × 按钮关闭；底部显示名称与原始尺寸。
 */
export default function ImageLightbox({ src, alt, onClose }) {
  const [visible, setVisible] = useState(false);
  const [naturalSize, setNaturalSize] = useState(null); // {w, h}

  const handleClose = useCallback(() => {
    setVisible(false);
    setTimeout(onClose, 150); // 等淡出动画结束再卸载
  }, [onClose]);

  // 入场动画 + Esc 关闭 + 锁 body 滚动
  useEffect(() => {
    const raf = requestAnimationFrame(() => setVisible(true));
    const onKey = (e) => { if (e.key === 'Escape') handleClose(); };
    document.addEventListener('keydown', onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      cancelAnimationFrame(raf);
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [handleClose]);

  if (!src) return null;

  return (
    <div
      className={`fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm transition-opacity duration-150 ${visible ? 'opacity-100' : 'opacity-0'}`}
      onClick={handleClose}
    >
      <button
        onClick={handleClose}
        title="关闭 (Esc)"
        className="absolute top-4 right-4 w-9 h-9 flex items-center justify-center rounded-full bg-surface/10 hover:bg-surface/20 text-body transition-colors"
      >
        <i className="fas fa-times"></i>
      </button>
      <div
        className={`flex flex-col items-center gap-2 max-w-[88vw] transition-all duration-150 ${visible ? 'scale-100 opacity-100' : 'scale-95 opacity-0'}`}
        onClick={(e) => e.stopPropagation()}
      >
        <img
          src={src}
          alt={alt || '截图预览'}
          onLoad={(e) => setNaturalSize({ w: e.target.naturalWidth, h: e.target.naturalHeight })}
          className="max-w-full max-h-[82vh] object-contain bg-surface rounded-lg shadow-2xl"
        />
        <div className="text-xs text-muted">
          {alt || '截图预览'}
          {naturalSize && <span className="ml-2 text-faint">{naturalSize.w} × {naturalSize.h}</span>}
        </div>
      </div>
    </div>
  );
}
