import { useState, useEffect } from 'react';
import { Menu, Button, message, Select, Space, Modal, Input, Popconfirm } from 'antd';
import {
  FileOutlined,
  MessageOutlined,
  SettingOutlined,
  PlusOutlined,
  DeleteOutlined,
  DatabaseOutlined,
} from '@ant-design/icons';
import type { Conversation, KnowledgeBase } from '../types';
import { listConversations, deleteConversation, listKBs, createKB, deleteKB } from '../services/api';
import DocumentList from './DocumentList';
import SettingsPanel from './SettingsPanel';

type Tab = 'documents' | 'conversations' | 'settings';

interface Props {
  currentConversationId: number | null;
  onSelectConversation: (id: number | null) => void;
  refreshTrigger: number;
  onDocumentClick?: (docId: number) => void;
  currentKbId: number;
  onKbChange: (kbId: number) => void;
}

export default function Sidebar({ currentConversationId, onSelectConversation, refreshTrigger, onDocumentClick, currentKbId, onKbChange }: Props) {
  const [tab, setTab] = useState<Tab>('conversations');
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [createKbOpen, setCreateKbOpen] = useState(false);
  const [newKbName, setNewKbName] = useState('');
  const [newKbDesc, setNewKbDesc] = useState('');

  const loadConversations = async () => {
    try {
      const data = await listConversations();
      setConversations(data);
    } catch (e: any) {
      message.error(e.message);
    }
  };

  const loadKBs = async () => {
    try {
      const data = await listKBs();
      setKbs(data);
    } catch (e: any) {
      message.error(e.message);
    }
  };

  useEffect(() => {
    loadKBs();
  }, []);

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

  const handleCreateKb = async () => {
    if (!newKbName.trim()) return;
    try {
      await createKB({ name: newKbName.trim(), description: newKbDesc.trim() || undefined });
      message.success('知识库创建成功');
      setCreateKbOpen(false);
      setNewKbName('');
      setNewKbDesc('');
      await loadKBs();
    } catch (e: any) {
      message.error(e.message);
    }
  };

  const handleDeleteKb = async (kbId: number) => {
    try {
      await deleteKB(kbId);
      message.success('已删除');
      if (currentKbId === kbId) {
        onKbChange(1);
      }
      await loadKBs();
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
      {/* KB Selector */}
      <div style={{ padding: '8px 12px', borderBottom: '1px solid #f0f0f0' }}>
        <Space style={{ width: '100%' }} align="center">
          <DatabaseOutlined style={{ color: '#1677ff' }} />
          <Select
            value={currentKbId}
            onChange={onKbChange}
            style={{ flex: 1, minWidth: 120 }}
            size="small"
            options={kbs.map((kb) => ({ value: kb.id, label: kb.name }))}
          />
          <Button
            type="text"
            size="small"
            icon={<PlusOutlined />}
            onClick={() => setCreateKbOpen(true)}
          />
          {currentKbId !== 1 && (
            <Popconfirm
              title="确认删除此知识库？"
              description="知识库必须为空才能删除"
              onConfirm={() => handleDeleteKb(currentKbId)}
            >
              <Button type="text" size="small" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          )}
        </Space>
      </div>

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

        {tab === 'documents' && <DocumentList onDocumentClick={onDocumentClick} currentKbId={currentKbId} />}
        {tab === 'settings' && <SettingsPanel />}
      </div>

      {/* Create KB Modal */}
      <Modal
        title="新建知识库"
        open={createKbOpen}
        onOk={handleCreateKb}
        onCancel={() => { setCreateKbOpen(false); setNewKbName(''); setNewKbDesc(''); }}
        okButtonProps={{ disabled: !newKbName.trim() }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, paddingTop: 8 }}>
          <Input
            placeholder="知识库名称"
            value={newKbName}
            onChange={(e) => setNewKbName(e.target.value)}
          />
          <Input.TextArea
            placeholder="描述（可选）"
            value={newKbDesc}
            onChange={(e) => setNewKbDesc(e.target.value)}
            autoSize={{ minRows: 2, maxRows: 4 }}
          />
        </div>
      </Modal>
    </div>
  );
}
