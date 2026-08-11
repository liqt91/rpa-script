import { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react';
import { api } from '../api';

const ActiveRunContext = createContext(null);

export function ActiveRunProvider({ children }) {
  const [activeRun, setActiveRun] = useState(null);
  const [loading, setLoading] = useState(true);
  const [runResult, setRunResult] = useState(null); // {workflow_id, run_id, kind, error} 侧边栏结果卡
  const mountedRef = useRef(true);

  const notifyRunStarted = useCallback((workflow_id, run_id) => {
    setRunResult(null);
    setActiveRun((prev) => prev ?? { workflow_id, run_id });
  }, []);

  // 运行结束结果（侧边栏卡片展示）；success/stopped 4s 自动清除，error 停留
  const notifyRunFinished = useCallback((result) => {
    setRunResult(result);
    if (result.kind !== 'error') {
      setTimeout(() => {
        setRunResult((cur) => (cur && cur.run_id === result.run_id ? null : cur));
      }, 4000);
    }
  }, []);

  const clearRunResult = useCallback(() => setRunResult(null), []);

  const refresh = useCallback(async () => {
    try {
      const runs = await api.getActiveRuns();
      if (!mountedRef.current) return;
      const first = Array.isArray(runs) && runs.length > 0 ? runs[0] : null;
      setActiveRun(first);
    } catch (e) {
      if (mountedRef.current) {
        console.error('[ActiveRun] refresh failed:', e);
      }
    } finally {
      if (mountedRef.current) {
        setLoading(false);
      }
    }
  }, []);

  const stopActiveRun = useCallback(async () => {
    if (!activeRun) return;
    try {
      await api.stopActiveRun();
      setActiveRun(null);
      await refresh();
    } catch (e) {
      console.error('[ActiveRun] stop failed:', e);
      alert('停止失败: ' + (e.message || '未知错误'));
    }
  }, [activeRun, refresh]);

  useEffect(() => {
    mountedRef.current = true;
    refresh();
    const id = setInterval(refresh, 2000);
    return () => {
      mountedRef.current = false;
      clearInterval(id);
    };
  }, [refresh]);

  return (
    <ActiveRunContext.Provider value={{ activeRun, isBusy: !!activeRun, loading, refresh, notifyRunStarted, notifyRunFinished, runResult, clearRunResult, stopActiveRun }}>
      {children}
    </ActiveRunContext.Provider>
  );
}

export function useActiveRun() {
  const ctx = useContext(ActiveRunContext);
  if (!ctx) {
    throw new Error('useActiveRun must be used within ActiveRunProvider');
  }
  return ctx;
}
