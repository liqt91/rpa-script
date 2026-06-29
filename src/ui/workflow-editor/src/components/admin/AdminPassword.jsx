import { useState } from 'react';
import { api } from '../../api';

export default function AdminPassword() {
  const [form, setForm] = useState({ old_password: '', new_password: '', confirm_password: '' });
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState('');
  const [error, setError] = useState('');

  async function handleSubmit(e) {
    e.preventDefault();
    setSuccess('');
    setError('');
    if (form.new_password !== form.confirm_password) {
      setError('两次输入的新密码不一致');
      return;
    }
    if (form.new_password.length < 6) {
      setError('新密码长度至少为 6 位');
      return;
    }
    setLoading(true);
    try {
      await api.changePassword({
        old_password: form.old_password,
        new_password: form.new_password,
      });
      setSuccess('密码修改成功');
      setForm({ old_password: '', new_password: '', confirm_password: '' });
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="p-6 max-w-xl">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-white">修改密码</h1>
        <p className="text-gray-500 text-sm mt-1">修改当前登录用户的密码</p>
      </div>

      {success && (
        <div className="mb-4 p-3 bg-green-900/30 border border-green-700 rounded-lg text-green-300 text-sm">
          <i className="fas fa-check-circle mr-2"></i>{success}
          <button onClick={() => setSuccess('')} className="ml-2 text-green-400 hover:text-green-200">×</button>
        </div>
      )}
      {error && (
        <div className="mb-4 p-3 bg-red-900/30 border border-red-700 rounded-lg text-red-300 text-sm">
          <i className="fas fa-exclamation-circle mr-2"></i>{error}
          <button onClick={() => setError('')} className="ml-2 text-red-400 hover:text-red-200">×</button>
        </div>
      )}

      <form onSubmit={handleSubmit} className="bg-[#1e293b] rounded-xl border border-gray-700 p-6 space-y-4">
        <div>
          <label className="block text-sm text-gray-400 mb-1.5">原密码</label>
          <input
            type="password"
            value={form.old_password}
            onChange={e => setForm(f => ({ ...f, old_password: e.target.value }))}
            required
            className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded-lg text-white text-sm"
          />
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-1.5">新密码</label>
          <input
            type="password"
            value={form.new_password}
            onChange={e => setForm(f => ({ ...f, new_password: e.target.value }))}
            required
            className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded-lg text-white text-sm"
          />
          <p className="text-xs text-gray-500 mt-1">至少 6 位</p>
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-1.5">确认新密码</label>
          <input
            type="password"
            value={form.confirm_password}
            onChange={e => setForm(f => ({ ...f, confirm_password: e.target.value }))}
            required
            className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded-lg text-white text-sm"
          />
        </div>
        <div className="pt-2">
          <button
            type="submit"
            disabled={loading}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800/50 text-white rounded-lg text-sm font-medium"
          >
            {loading && <i className="fas fa-circle-notch fa-spin mr-2"></i>}
            保存
          </button>
        </div>
      </form>
    </div>
  );
}
