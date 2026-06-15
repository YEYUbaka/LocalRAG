import { useState, useEffect } from 'react';
import { List, Button, Upload, message, Tag, Popconfirm, Typography } from 'antd';
import { UploadOutlined, DeleteOutlined, FilePdfOutlined, FileTextOutlined, FileWordOutlined, InboxOutlined } from '@ant-design/icons';
import type { UploadFile } from 'antd/es/upload/interface';
import type { Document } from '../types';
import { listDocuments, uploadDocument, deleteDocument, getDocumentStatus } from '../services/api';

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
      const data = await listDocuments(currentKbId);
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

  return (
    <div style={{ padding: '0 8px' }}>
      <Dragger
        multiple
        showUploadList={false}
        accept=".pdf,.docx,.doc,.md,.txt"
        beforeUpload={handleUpload}
        disabled={loading}
        style={{ marginBottom: 16, padding: '16px 0' }}
      >
        <p className="ant-upload-drag-icon">
          <InboxOutlined />
        </p>
        <p className="ant-upload-text">点击或拖拽文件到此处上传</p>
        <p className="ant-upload-hint">支持 PDF、Word、Markdown、TXT 格式</p>
      </Dragger>
      <List
        size="small"
        dataSource={docs}
        locale={{ emptyText: '暂无文档' }}
        renderItem={(doc) => (
          <List.Item
            onClick={() => doc.status === 'completed' && onDocumentClick?.(doc.id)}
            style={{ cursor: doc.status === 'completed' ? 'pointer' : 'default' }}
            actions={[
              <Popconfirm title="确认删除？" onConfirm={() => handleDelete(doc.id)}>
                <Button type="text" danger icon={<DeleteOutlined />} size="small" />
              </Popconfirm>,
            ]}
          >
            <List.Item.Meta
              avatar={getIcon(doc.filename)}
              title={<span style={{ fontSize: 13 }}>{doc.filename}</span>}
              description={
                <div>
                  <Tag color={STATUS_MAP[doc.status]?.color}>
                    {STATUS_MAP[doc.status]?.text}
                  </Tag>
                  {doc.chunk_count > 0 && (
                    <Text type="secondary" style={{ fontSize: 11, marginLeft: 4 }}>
                      {doc.chunk_count} chunks
                    </Text>
                  )}
                </div>
              }
            />
          </List.Item>
        )}
      />
    </div>
  );
}
