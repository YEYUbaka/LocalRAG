import type { Document, Conversation, Settings, DocumentContent, KnowledgeBase } from '../types';

const BASE = '/api';

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, options);
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

export async function listDocuments(kbId?: number): Promise<Document[]> {
  const params = kbId !== undefined ? `?kb_id=${kbId}` : '';
  return request(`/documents${params}`);
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

// Settings
export async function getSettings(): Promise<Settings> {
  return request('/settings');
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
