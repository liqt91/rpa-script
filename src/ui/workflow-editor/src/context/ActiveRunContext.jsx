import { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react';
import { api } from '../api';

const ActiveRunContext = createContext(null);

export function ActiveRunProvider({ children }) {
  const [activeRun, setActiveRun] = useState(null);
  const [loading, setLoading] = useState(true);
  const mountedRef = useRef(true);

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
      await refresh();
    } catch (e) {
      console.error('[ActiveRun] stop failed:', e);
      alert('停止失败: ' + (e.message || '未知错误'));
    }
  }, [activeRun, refresh]);

  useEffect(() => {
    mountedRef.current = true;
    refresh();
    const id = setInterval(refresh, 3000);
    return () => {
      mountedRef.current = false;
      clearInterval(id);
    };
  }, [refresh]);

  return (
    <ActiveRunContext.Provider value={{ activeRun, isBusy: !!activeRun, loading, refresh, stopActiveRun }}>
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
