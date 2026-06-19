import { useState, useEffect } from 'react';
import { Button, Upload, message, Tag, Popconfirm, Typography, Space } from 'antd';
import { UploadOutlined, DeleteOutlined, FilePdfOutlined, FileTextOutlined, FileWordOutlined, InboxOutlined, ReloadOutlined } from '@ant-design/icons';
import type { Document } from '../types';
import { listDocuments, uploadDocument, deleteDocument, getDocumentStatus, reprocessDocument } from '../services/api';

const { Dragger } = Upload;
const { Text } = Typography;

const STATUS_MAP: Record<string, { color: string; text: string }> = {
  pending: { color: 'default', text: '等待处理' },
  processing: { color: 'processing', text: '处理中' },
  completed: { color: 'success', text: '已完成' },
  failed: { color: 'error', text: '失败' },
};

function getIcon(filename: string) {
  const ext = filename.split('.').pop()?.toLowerCase();
  if (ext === 'pdf') return <FilePdfOutlined />;
  if (ext === 'docx' || ext === 'doc') return <FileWordOutlined />;
  return <FileTextOutlined />;
}

interface Props {
  onDocumentClick?: (docId: number) => void;
  currentKbId: number;
}

export default function DocumentList({ onDocumentClick, currentKbId }: Props) {
  const [docs, setDocs] = useState<Document[]>([]);
  const [loading, setLoading] = useState(false);

  const loadDocs = async () => {
    try {
      const data = await listDocuments({ kbId: currentKbId });
      setDocs(data);
    } catch (e: any) {
      message.error(e.message);
    }
  };

  useEffect(() => {
    loadDocs();
  }, [currentKbId]);

  const handleUpload = async (file: File) => {
    setLoading(true);
    try {
      const result = await uploadDocument(file, currentKbId);
      message.success(`上传成功: ${result.filename}`);
      await loadDocs();
      pollStatus(result.id);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
    return false;
  };

  const pollStatus = (docId: number) => {
    const interval = setInterval(async () => {
      try {
        const status = await getDocumentStatus(docId);
        if (status.status === 'completed' || status.status === 'failed') {
          clearInterval(interval);
          await loadDocs();
          if (status.status === 'failed') {
            message.error(`文档处理失败: ${status.error_message}`);
          }
        }
      } catch {
        clearInterval(interval);
      }
    }, 2000);
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteDocument(id);
      message.success('已删除');
      await loadDocs();
    } catch (e: any) {
      message.error(e.message);
    }
  };

  const handleReprocess = async (id: number) => {
    try {
      await reprocessDocument(id);
      message.success('已开始重新处理');
      await loadDocs();
      pollStatus(id);
    } catch (e: any) {
      message.error(e.message);
    }
  };

  return (
    <div style={{ padding: '0 8px' }}>
      <Dragger
        multiple
        showUploadList={false}
        accept=".pdf,.docx,.doc,.md,.txt,.xlsx,.pptx,.html,.htm,.csv"
        beforeUpload={handleUpload}
        disabled={loading}
        style={{ marginBottom: 16, padding: '16px 0' }}
      >
        <p className="ant-upload-drag-icon">
          <InboxOutlined />
        </p>
        <p className="ant-upload-text">点击或拖拽文件到此处上传</p>
        <p className="ant-upload-hint">支持 PDF、Word、Markdown、TXT、Excel、PPT、HTML、CSV 格式</p>
      </Dragger>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {docs.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 24, color: '#999' }}>暂无文档</div>
        ) : (
          docs.map((doc) => (
            <div
              key={doc.id}
              onClick={() => doc.status === 'completed' && onDocumentClick?.(doc.id)}
              style={{
                cursor: doc.status === 'completed' ? 'pointer' : 'default',
                padding: '12px 16px',
                border: '1px solid #f0f0f0',
                borderRadius: 8,
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                transition: 'all 0.2s',
                backgroundColor: doc.status === 'completed' ? '#fafafa' : '#fff',
              }}
              onMouseEnter={(e) => {
                if (doc.status === 'completed') {
                  e.currentTarget.style.borderColor = '#d9d9d9';
                  e.currentTarget.style.backgroundColor = '#f5f5f5';
                }
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = '#f0f0f0';
                e.currentTarget.style.backgroundColor = doc.status === 'completed' ? '#fafafa' : '#fff';
              }}
            >
              <div style={{ fontSize: 20, color: '#1890ff' }}>
                {getIcon(doc.filename)}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {doc.filename}
                </div>
                <Space size={4}>
                  <Tag color={STATUS_MAP[doc.status]?.color} style={{ margin: 0 }}>
                    {STATUS_MAP[doc.status]?.text}
                  </Tag>
                  {doc.chunk_count > 0 && (
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {doc.chunk_count} chunks
                    </Text>
                  )}
                </Space>
              </div>
              <Space size={4}>
                {(doc.status === 'completed' || doc.status === 'failed') && (
                  <Button
                    type="text"
                    icon={<ReloadOutlined />}
                    size="small"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleReprocess(doc.id);
                    }}
                  />
                )}
                <Popconfirm
                  title="确认删除？"
                  onConfirm={() => handleDelete(doc.id)}
                  onCancel={(e) => e?.stopPropagation()}
                >
                  <Button
                    type="text"
                    danger
                    icon={<DeleteOutlined />}
                    size="small"
                    onClick={(e) => e.stopPropagation()}
                  />
                </Popconfirm>
              </Space>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
