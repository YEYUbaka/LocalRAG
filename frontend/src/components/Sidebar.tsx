import { useState, useEffect } from 'react';
import { Menu, Button, message } from 'antd';
import {
  FileOutlined,
  MessageOutlined,
  SettingOutlined,
  PlusOutlined,
  DeleteOutlined,
} from '@ant-design/icons';
import type { Conversation } from '../types';
import { listConversations, deleteConversation } from '../services/api';
import DocumentList from './DocumentList';
import SettingsPanel from './SettingsPanel';

type Tab = 'documents' | 'conversations' | 'settings';

interface Props {
  currentConversationId: number | null;
  onSelectConversation: (id: number | null) => void;
  refreshTrigger: number;
  onDocumentClick?: (docId: number) => void;
}

export default function Sidebar({ currentConversationId, onSelectConversation, refreshTrigger, onDocumentClick }: Props) {
  const [tab, setTab] = useState<Tab>('conversations');
  const [conversations, setConversations] = useState<Conversation[]>([]);

  const loadConversations = async () => {
    try {
      const data = await listConversations();
      setConversations(data);
    } catch (e: any) {
      message.error(e.message);
    }
  };

  useEffect(() => {
    if (tab === 'conversations') {
      loadConversations();
    }
  }, [tab, refreshTrigger]);

  const handleDeleteConv = async (id: number, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await deleteConversation(id);
      if (currentConversationId === id) {
        onSelectConversation(null);
      }
      await loadConversations();
    } catch (e: any) {
      message.error(e.message);
    }
  };

  const menuItems = [
    { key: 'conversations', icon: <MessageOutlined />, label: '对话' },
    { key: 'documents', icon: <FileOutlined />, label: '文档' },
    { key: 'settings', icon: <SettingOutlined />, label: '设置' },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Menu
        mode="horizontal"
        selectedKeys={[tab]}
        items={menuItems}
        onClick={({ key }) => setTab(key as Tab)}
        style={{ borderBottom: '1px solid #f0f0f0' }}
      />

      <div style={{ flex: 1, overflow: 'auto' }}>
        {tab === 'conversations' && (
          <div style={{ padding: '8px' }}>
            <Button
              icon={<PlusOutlined />}
              block
              style={{ marginBottom: 8 }}
              onClick={() => onSelectConversation(null)}
            >
              新对话
            </Button>
            {conversations.map((conv) => (
              <div
                key={conv.id}
                onClick={() => onSelectConversation(conv.id)}
                style={{
                  padding: '8px 12px',
                  marginBottom: 4,
                  borderRadius: 8,
                  cursor: 'pointer',
                  background: currentConversationId === conv.id ? '#e6f4ff' : 'transparent',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <span style={{ fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {conv.title}
                </span>
                <Button
                  type="text"
                  size="small"
                  icon={<DeleteOutlined />}
                  onClick={(e) => handleDeleteConv(conv.id, e)}
                />
              </div>
            ))}
            {conversations.length === 0 && (
              <div style={{ textAlign: 'center', color: '#999', padding: 20, fontSize: 13 }}>
                暂无对话
              </div>
            )}
          </div>
        )}

        {tab === 'documents' && <DocumentList onDocumentClick={onDocumentClick} />}
        {tab === 'settings' && <SettingsPanel />}
      </div>
    </div>
  );
}
