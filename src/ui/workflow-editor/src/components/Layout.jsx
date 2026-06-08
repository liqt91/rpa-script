import { useEffect, useLayoutEffect, useRef } from 'react';
import { useWorkflow } from '../store/WorkflowContext';
import Toolbar from './Toolbar';
import CommandPanel from './CommandPanel';
import NodeList from './NodeList';
import NodeForm from './NodeForm';
import ElementLibraryTab from './ElementLibraryTab';

const LAYOUT_KEY = 'wf_editor_layout';

export default function Layout() {
  const { loadWorkflow, loadElements } = useWorkflow();
  const leftRef = useRef(null);
  const rightRef = useRef(null);
  const bottomRef = useRef(null);

  useEffect(() => {
    loadWorkflow();
    loadElements();
  }, []);

  function restoreLayout() {
    try {
      const saved = JSON.parse(localStorage.getItem(LAYOUT_KEY) || '{}');
      if (saved.leftWidth && leftRef.current?.previousElementSibling) {
        leftRef.current.previousElementSibling.style.width = saved.leftWidth + 'px';
      }
      if (saved.rightWidth && rightRef.current?.nextElementSibling) {
        rightRef.current.nextElementSibling.style.width = saved.rightWidth + 'px';
      }
      if (saved.bottomHeight && bottomRef.current?.nextElementSibling) {
        bottomRef.current.nextElementSibling.style.height = saved.bottomHeight + 'px';
      }
    } catch {
      // ignore
    }
  }

  // 恢复保存的布局尺寸（在绘制前执行，避免闪烁；并延迟一次确保子组件已稳定）
  useLayoutEffect(() => {
    restoreLayout();
    const id = requestAnimationFrame(() => restoreLayout());
    return () => cancelAnimationFrame(id);
  }, []);

  function initResize(handle, direction) {
    let startX, startY, startWidth, startHeight, targetEl;

    handle.addEventListener('mousedown', (e) => {
      e.preventDefault();
      document.body.classList.add('resizing-active');
      handle.classList.add('resizing');

      if (direction === 'left') {
        targetEl = handle.previousElementSibling;
        startX = e.clientX;
        startWidth = targetEl.offsetWidth;
      } else if (direction === 'right') {
        targetEl = handle.nextElementSibling;
        startX = e.clientX;
        startWidth = targetEl.offsetWidth;
      } else if (direction === 'bottom') {
        targetEl = handle.nextElementSibling;
        startY = e.clientY;
        startHeight = targetEl.offsetHeight;
      }

      document.addEventListener('mousemove', onMouseMove);
      document.addEventListener('mouseup', onMouseUp);
    });

    function onMouseMove(e) {
      if (direction === 'left') {
        const newWidth = startWidth + (e.clientX - startX);
        if (newWidth >= 180 && newWidth <= 500) {
          targetEl.style.width = newWidth + 'px';
        }
      } else if (direction === 'right') {
        const newWidth = startWidth - (e.clientX - startX);
        if (newWidth >= 180 && newWidth <= 500) {
          targetEl.style.width = newWidth + 'px';
        }
      } else if (direction === 'bottom') {
        const newHeight = startHeight - (e.clientY - startY);
        if (newHeight >= 80 && newHeight <= 600) {
          targetEl.style.height = newHeight + 'px';
        }
      }
    }

    function onMouseUp() {
      document.body.classList.remove('resizing-active');
      handle.classList.remove('resizing');
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);

      try {
        const saved = JSON.parse(localStorage.getItem(LAYOUT_KEY) || '{}');
        if (targetEl) {
          if (direction === 'left') saved.leftWidth = targetEl.offsetWidth;
          else if (direction === 'right') saved.rightWidth = targetEl.offsetWidth;
          else if (direction === 'bottom') saved.bottomHeight = targetEl.offsetHeight;
          localStorage.setItem(LAYOUT_KEY, JSON.stringify(saved));
        }
      } catch {
        // ignore
      }
    }
  }

  useEffect(() => {
    if (leftRef.current) initResize(leftRef.current, 'left');
    if (rightRef.current) initResize(rightRef.current, 'right');
    if (bottomRef.current) initResize(bottomRef.current, 'bottom');
  }, []);

  return (
    <div className="h-screen flex flex-col bg-[#f0f2f5] overflow-hidden">
      <Toolbar />
      <div className="flex flex-1 min-h-0">
        <CommandPanel />
        <div className="resize-handle-v shrink-0" ref={leftRef} title="拖动调整左侧面板宽度" />
        <NodeList />
        <div className="resize-handle-v shrink-0" ref={rightRef} title="拖动调整右侧面板宽度" />
        <NodeForm />
      </div>
      <div className="resize-handle-h shrink-0" ref={bottomRef} title="拖动调整底部面板高度" />
      <ElementLibraryTab />
    </div>
  );
}
