import type { Document, Conversation, Settings, DocumentContent, KnowledgeBase, Tag, BatchImportResponse } from '../types';

const BASE = '/api';

function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem('token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const headers = { ...getAuthHeaders(), ...options?.headers };
  const res = await fetch(`${BASE}${url}`, { ...options, headers });
  if (res.status === 401) {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    window.location.reload();
    throw new Error('认证已过期，请重新登录');
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || '请求失败');
  }
  return res.json();
}

// Documents
export async function uploadDocument(file: File, kbId: number = 1): Promise<{ id: number; filename: string; status: string }> {
  const form = new FormData();
  form.append('file', file);
  form.append('kb_id', String(kbId));
  return request('/documents/upload', { method: 'POST', body: form });
}

export async function listDocuments(opts?: { kbId?: number; search?: string; status?: string; tagId?: number }): Promise<Document[]> {
  const params = new URLSearchParams();
  if (opts?.kbId !== undefined) params.set('kb_id', String(opts.kbId));
  if (opts?.search) params.set('search', opts.search);
  if (opts?.status) params.set('status', opts.status);
  if (opts?.tagId !== undefined) params.set('tag_id', String(opts.tagId));
  const qs = params.toString();
  return request(`/documents${qs ? '?' + qs : ''}`);
}

export async function getDocumentStatus(id: number): Promise<{ id: number; status: string; error_message: string | null }> {
  return request(`/documents/${id}/status`);
}

export async function deleteDocument(id: number): Promise<void> {
  await request(`/documents/${id}`, { method: 'DELETE' });
}

export async function reprocessDocument(id: number): Promise<{ id: number; status: string }> {
  return request(`/documents/${id}/reprocess`, { method: 'POST' });
}

export async function getDocumentContent(id: number): Promise<DocumentContent> {
  return request(`/documents/${id}/content`);
}

export async function importUrl(url: string, kbId: number = 1): Promise<{ id: number; filename: string; status: string }> {
  return request('/documents/import-url', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, kb_id: kbId }),
  });
}

export async function importBatchUrls(urls: string[], kbId: number = 1): Promise<BatchImportResponse> {
  return request('/documents/import-batch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ urls, kb_id: kbId }),
  });
}

export async function importCrawlSite(url: string, kbId: number = 1, maxPages: number = 20, maxDepth: number = 2): Promise<{ id: number; filename: string; status: string }> {
  return request('/documents/import-crawl', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, kb_id: kbId, max_pages: maxPages, max_depth: maxDepth }),
  });
}

// Chat
export async function listConversations(): Promise<Conversation[]> {
  return request('/chat/history');
}

export async function getConversation(id: number): Promise<Conversation> {
  return request(`/chat/${id}`);
}

export async function deleteConversation(id: number): Promise<void> {
  await request(`/chat/${id}`, { method: 'DELETE' });
}

// Export
export function getExportUrl(conversationId: number): string {
  return `${BASE}/export/conversation/${conversationId}`;
}

// Settings
export async function getSettings(): Promise<Settings> {
  return request('/settings');
}

// Image Analysis
export async function analyzeImage(
  question: string,
  imageBase64: string,
  conversationId: number | null,
  kbId?: number | null,
): Promise<Response> {
  const token = localStorage.getItem('token');
  const res = await fetch('/api/chat/image', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      question,
      image_base64: imageBase64,
      conversation_id: conversationId,
      kb_id: kbId,
    }),
  });
  return res;
}

export async function updateSettings(data: Partial<Settings> & { llm_api_key?: string }): Promise<Settings> {
  return request('/settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
}

// Knowledge Bases
export async function listKBs(): Promise<KnowledgeBase[]> {
  return request('/kb');
}

export async function createKB(data: { name: string; description?: string }): Promise<{ id: number; name: string; description: string | null }> {
  return request('/kb', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
}

export async function deleteKB(id: number): Promise<void> {
  await request(`/kb/${id}`, { method: 'DELETE' });
}

// Tags
export async function listTags(): Promise<Tag[]> {
  return request('/tags');
}

export async function createTag(name: string, color: string = 'default'): Promise<Tag> {
  return request('/tags', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, color }),
  });
}

export async function deleteTag(id: number): Promise<void> {
  await request(`/tags/${id}`, { method: 'DELETE' });
}

export async function attachTag(documentId: number, tagId: number): Promise<void> {
  await request(`/tags/attach?document_id=${documentId}&tag_id=${tagId}`, { method: 'POST' });
}

export async function detachTag(documentId: number, tagId: number): Promise<void> {
  await request(`/tags/detach?document_id=${documentId}&tag_id=${tagId}`, { method: 'POST' });
}

// Auth
export async function login(username: string, password: string): Promise<{ token: string; user: { id: number; username: string } }> {
  const result = await request<{ token: string; user: { id: number; username: string } }>('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  localStorage.setItem('token', result.token);
  localStorage.setItem('user', JSON.stringify(result.user));
  return result;
}

export async function register(username: string, password: string): Promise<{ token: string; user: { id: number; username: string } }> {
  const result = await request<{ token: string; user: { id: number; username: string } }>('/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  localStorage.setItem('token', result.token);
  localStorage.setItem('user', JSON.stringify(result.user));
  return result;
}

export function logout(): void {
  localStorage.removeItem('token');
  localStorage.removeItem('user');
}

export function getStoredUser(): { id: number; username: string } | null {
  const userStr = localStorage.getItem('user');
  if (!userStr) return null;
  try {
    return JSON.parse(userStr);
  } catch {
    return null;
  }
}

export function isAuthenticated(): boolean {
  return !!localStorage.getItem('token');
}
