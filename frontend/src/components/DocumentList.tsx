import { useState, useEffect, useRef, useCallback } from 'react';
import { Button, Upload, message, Tag, Popconfirm, Typography, Space, Input, Select, Popover, Checkbox, Tabs, InputNumber } from 'antd';
import {
  DeleteOutlined, FilePdfOutlined, FileTextOutlined,
  FileWordOutlined, InboxOutlined, ReloadOutlined, SearchOutlined,
  TagsOutlined, PlusOutlined, LinkOutlined, GlobalOutlined,
} from '@ant-design/icons';
import type { Document, Tag as TagType, BatchImportResult } from '../types';
import { listDocuments, uploadDocument, deleteDocument, getDocumentStatus, reprocessDocument, listTags, createTag, attachTag, detachTag, importUrl, importBatchUrls, importCrawlSite } from '../services/api';
import { getErrorMessage } from '../services/errors';

const { Dragger } = Upload;
const { Text } = Typography;

const STATUS_MAP: Record<string, { color: string; text: string }> = {
  pending: { color: 'default', text: '等待处理' },
  processing: { color: 'processing', text: '处理中' },
  completed: { color: 'success', text: '已完成' },
  failed: { color: 'error', text: '失败' },
};

const TAG_COLORS = ['default', 'blue', 'green', 'orange', 'red', 'purple', 'cyan', 'magenta', 'gold', 'lime'];

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
  const [searchText, setSearchText] = useState('');
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [tagFilter, setTagFilter] = useState<number | undefined>(undefined);
  const [allTags, setAllTags] = useState<TagType[]>([]);
  const [tagPopoverDoc, setTagPopoverDoc] = useState<number | null>(null);
  const [newTagName, setNewTagName] = useState('');
  const [newTagColor, setNewTagColor] = useState('default');
  const [urlInput, setUrlInput] = useState('');
  const [batchUrls, setBatchUrls] = useState('');
  const [crawlUrl, setCrawlUrl] = useState('');
  const [maxPages, setMaxPages] = useState(20);
  const [maxDepth, setMaxDepth] = useState(2);
  const [importing, setImporting] = useState(false);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadDocs = useCallback(async () => {
    try {
      const data = await listDocuments({
        kbId: currentKbId,
        search: searchText || undefined,
        status: statusFilter,
        tagId: tagFilter,
      });
      setDocs(data);
    } catch (e: unknown) {
      message.error(getErrorMessage(e));
    }
  }, [currentKbId, searchText, statusFilter, tagFilter]);

  const loadTags = useCallback(async () => {
    try {
      const data = await listTags();
      setAllTags(data);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      void loadTags();
    }, 0);
    return () => clearTimeout(timer);
  }, [loadTags]);

  // Debounced search
  useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => {
      void loadDocs();
    }, 300);
    return () => { if (searchTimer.current) clearTimeout(searchTimer.current); };
  }, [loadDocs]);

  const handleUpload = async (file: File) => {
    setLoading(true);
    try {
      const result = await uploadDocument(file, currentKbId);
      message.success(`上传成功: ${result.filename}`);
      await loadDocs();
      pollStatus(result.id);
    } catch (e: unknown) {
      message.error(getErrorMessage(e));
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
    } catch (e: unknown) {
      message.error(getErrorMessage(e));
    }
  };

  const handleReprocess = async (id: number) => {
    try {
      await reprocessDocument(id);
      message.success('已开始重新处理');
      await loadDocs();
      pollStatus(id);
    } catch (e: unknown) {
      message.error(getErrorMessage(e));
    }
  };

  const handleAttachTag = async (docId: number, tagId: number) => {
    try {
      await attachTag(docId, tagId);
      await loadDocs();
    } catch (e: unknown) {
      message.error(getErrorMessage(e));
    }
  };

  const handleDetachTag = async (docId: number, tagId: number) => {
    try {
      await detachTag(docId, tagId);
      await loadDocs();
    } catch (e: unknown) {
      message.error(getErrorMessage(e));
    }
  };

  const handleCreateTag = async () => {
    if (!newTagName.trim()) return;
    try {
      await createTag(newTagName.trim(), newTagColor);
      setNewTagName('');
      setNewTagColor('default');
      await loadTags();
      message.success('标签已创建');
    } catch (e: unknown) {
      message.error(getErrorMessage(e));
    }
  };

  const handleImportUrl = async () => {
    if (!urlInput.trim()) return;
    setImporting(true);
    try {
      const result = await importUrl(urlInput.trim(), currentKbId);
      message.success(`已提交: ${result.filename}`);
      setUrlInput('');
      await loadDocs();
      pollStatus(result.id);
    } catch (e: unknown) {
      message.error(getErrorMessage(e));
    } finally {
      setImporting(false);
    }
  };

  const handleBatchImport = async () => {
    const urls = batchUrls.split('\n').map(u => u.trim()).filter(Boolean);
    if (urls.length === 0) return;
    setImporting(true);
    try {
      const result = await importBatchUrls(urls, currentKbId);
      const pending = result.results.filter((r: BatchImportResult) => r.status === 'pending');
      message.success(`已提交 ${pending.length} 个 URL`);
      setBatchUrls('');
      await loadDocs();
      pending.forEach(d => pollStatus(d.id));
    } catch (e: unknown) {
      message.error(getErrorMessage(e));
    } finally {
      setImporting(false);
    }
  };

  const handleCrawlImport = async () => {
    if (!crawlUrl.trim()) return;
    setImporting(true);
    try {
      const result = await importCrawlSite(crawlUrl.trim(), currentKbId, maxPages, maxDepth);
      message.success(`爬取任务已提交: ${result.filename}`);
      setCrawlUrl('');
      await loadDocs();
      pollStatus(result.id);
    } catch (e: unknown) {
      message.error(getErrorMessage(e));
    } finally {
      setImporting(false);
    }
  };

  const renderTagPopover = (doc: Document) => {
    const docTagIds = new Set(doc.tags?.map(t => t.id));
    return (
      <div style={{ width: 220 }}>
        <div style={{ fontWeight: 500, marginBottom: 8 }}>管理标签</div>
        {allTags.length === 0 ? (
          <Text type="secondary" style={{ fontSize: 12 }}>暂无标签，请先创建</Text>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 8 }}>
            {allTags.map(tag => (
              <Checkbox
                key={tag.id}
                checked={docTagIds.has(tag.id)}
                onChange={(e) => {
                  if (e.target.checked) {
                    handleAttachTag(doc.id, tag.id);
                  } else {
                    handleDetachTag(doc.id, tag.id);
                  }
                }}
              >
                <Tag color={tag.color} style={{ margin: 0 }}>{tag.name}</Tag>
              </Checkbox>
            ))}
          </div>
        )}
        <div style={{ borderTop: '1px solid #f0f0f0', paddingTop: 8, marginTop: 4 }}>
          <div style={{ fontSize: 12, color: '#999', marginBottom: 4 }}>新建标签</div>
          <Space.Compact style={{ width: '100%' }}>
            <Input
              size="small"
              placeholder="标签名"
              value={newTagName}
              onChange={e => setNewTagName(e.target.value)}
              onPressEnter={handleCreateTag}
              style={{ flex: 1 }}
            />
            <Select
              size="small"
              value={newTagColor}
              onChange={setNewTagColor}
              style={{ width: 80 }}
              options={TAG_COLORS.map(c => ({ value: c, label: <Tag color={c} style={{ margin: 0, fontSize: 11 }}>{c}</Tag> }))}
            />
            <Button size="small" type="primary" icon={<PlusOutlined />} onClick={handleCreateTag} />
          </Space.Compact>
        </div>
      </div>
    );
  };

  return (
    <div style={{ padding: '0 8px' }}>
      {/* Search and Filter Bar */}
      <div style={{ marginBottom: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
        <Input
          placeholder="搜索文件名或内容..."
          prefix={<SearchOutlined style={{ color: '#bbb' }} />}
          value={searchText}
          onChange={e => setSearchText(e.target.value)}
          allowClear
          size="small"
        />
        <div style={{ display: 'flex', gap: 8 }}>
          <Select
            placeholder="状态"
            value={statusFilter}
            onChange={setStatusFilter}
            allowClear
            size="small"
            style={{ flex: 1 }}
            options={[
              { value: 'pending', label: '等待处理' },
              { value: 'processing', label: '处理中' },
              { value: 'completed', label: '已完成' },
              { value: 'failed', label: '失败' },
            ]}
          />
          <Select
            placeholder="标签"
            value={tagFilter}
            onChange={setTagFilter}
            allowClear
            size="small"
            style={{ flex: 1 }}
            options={allTags.map(t => ({ value: t.id, label: <Tag color={t.color} style={{ margin: 0 }}>{t.name}</Tag> }))}
          />
        </div>
      </div>

      {/* Upload & Import Area */}
      <Tabs
        size="small"
        items={[
          {
            key: 'upload',
            label: '文件上传',
            children: (
              <Dragger
                multiple
                showUploadList={false}
                accept=".pdf,.docx,.doc,.md,.txt,.xlsx,.pptx,.html,.htm,.csv"
                beforeUpload={handleUpload}
                disabled={loading}
                style={{ padding: '16px 0' }}
              >
                <p className="ant-upload-drag-icon">
                  <InboxOutlined />
                </p>
                <p className="ant-upload-text">点击或拖拽文件到此处上传</p>
                <p className="ant-upload-hint">支持 PDF、Word、Markdown、TXT、Excel、PPT、HTML、CSV 格式</p>
              </Dragger>
            ),
          },
          {
            key: 'single',
            label: '网页导入',
            children: (
              <div style={{ padding: '12px 0' }}>
                <Space.Compact style={{ width: '100%' }}>
                  <Input
                    prefix={<LinkOutlined />}
                    placeholder="输入网页 URL，如 https://example.com/article"
                    value={urlInput}
                    onChange={e => setUrlInput(e.target.value)}
                    onPressEnter={handleImportUrl}
                  />
                  <Button type="primary" loading={importing} onClick={handleImportUrl}>导入</Button>
                </Space.Compact>
              </div>
            ),
          },
          {
            key: 'batch',
            label: '批量导入',
            children: (
              <div style={{ padding: '12px 0' }}>
                <Input.TextArea
                  placeholder="每行一个 URL，支持同时导入多个网页"
                  value={batchUrls}
                  onChange={e => setBatchUrls(e.target.value)}
                  autoSize={{ minRows: 3, maxRows: 6 }}
                  style={{ marginBottom: 8 }}
                />
                <Button type="primary" block loading={importing} onClick={handleBatchImport}>
                  批量导入
                </Button>
              </div>
            ),
          },
          {
            key: 'crawl',
            label: '整站爬取',
            children: (
              <div style={{ padding: '12px 0' }}>
                <Input
                  prefix={<GlobalOutlined />}
                  placeholder="输入起始 URL，自动爬取同域名页面"
                  value={crawlUrl}
                  onChange={e => setCrawlUrl(e.target.value)}
                  style={{ marginBottom: 8 }}
                />
                <Space style={{ marginBottom: 8 }}>
                  <span style={{ fontSize: 12, color: '#666' }}>最大页面:</span>
                  <InputNumber size="small" value={maxPages} onChange={v => setMaxPages(v || 20)} min={1} max={50} />
                  <span style={{ fontSize: 12, color: '#666' }}>深度:</span>
                  <InputNumber size="small" value={maxDepth} onChange={v => setMaxDepth(v || 2)} min={1} max={3} />
                </Space>
                <Button type="primary" block loading={importing} onClick={handleCrawlImport}>
                  开始爬取
                </Button>
              </div>
            ),
          },
        ]}
        style={{ marginBottom: 16 }}
      />

      {/* Document List */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {docs.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 24, color: '#999' }}>
            {searchText || statusFilter || tagFilter ? '没有匹配的文档' : '暂无文档'}
          </div>
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
                <Space size={4} wrap>
                  <Tag color={STATUS_MAP[doc.status]?.color} style={{ margin: 0 }}>
                    {STATUS_MAP[doc.status]?.text}
                  </Tag>
                  {doc.chunk_count > 0 && (
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {doc.chunk_count} chunks
                    </Text>
                  )}
                  {doc.tags?.map(tag => (
                    <Tag
                      key={tag.id}
                      color={tag.color}
                      style={{ margin: 0, cursor: 'pointer' }}
                      closable
                      onClose={(e) => {
                        e.preventDefault();
                        handleDetachTag(doc.id, tag.id);
                      }}
                    >
                      {tag.name}
                    </Tag>
                  ))}
                </Space>
              </div>
              <Space size={4}>
                <Popover
                  content={renderTagPopover(doc)}
                  trigger="click"
                  open={tagPopoverDoc === doc.id}
                  onOpenChange={(open) => setTagPopoverDoc(open ? doc.id : null)}
                  placement="left"
                >
                  <Button
                    type="text"
                    icon={<TagsOutlined />}
                    size="small"
                    onClick={(e) => e.stopPropagation()}
                  />
                </Popover>
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
