import { useState, useEffect } from 'react';
import { Form, Input, Slider, InputNumber, Button, message, Space, Typography, Switch } from 'antd';
import type { Settings } from '../types';
import { getSettings, updateSettings } from '../services/api';

const { Text } = Typography;

export default function SettingsPanel() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [apiKey, setApiKey] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    getSettings()
      .then(setSettings)
      .catch((e) => message.error('加载设置失败: ' + e.message));
  }, []);

  const handleSave = async () => {
    if (!settings) return;
    setLoading(true);
    try {
      const payload: any = {
        llm_base_url: settings.llm_base_url,
        llm_model_name: settings.llm_model_name,
        top_k: settings.top_k,
        temperature: settings.temperature,
        max_tokens: settings.max_tokens,
        context_window: settings.context_window,
        similarity_threshold: settings.similarity_threshold,
        hybrid_search: settings.hybrid_search,
        bm25_weight: settings.bm25_weight,
        retrieval_top_k: settings.retrieval_top_k,
        rerank_top_k: settings.rerank_top_k,
        rerank_enabled: settings.rerank_enabled,
      };
      if (apiKey) {
        payload.llm_api_key = apiKey;
      }
      const updated = await updateSettings(payload);
      setSettings(updated);
      setApiKey('');
      message.success('设置已保存');
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  if (!settings) return null;

  return (
    <div style={{ padding: 16 }}>
      <Form layout="vertical">
        <Form.Item
          label="Base URL"
          tooltip="OpenAI 兼容 API 地址，如 https://dashscope.aliyuncs.com/compatible-mode/v1"
        >
          <Input
            value={settings.llm_base_url}
            onChange={(e) => setSettings({ ...settings, llm_base_url: e.target.value })}
            placeholder="https://api.openai.com/v1"
          />
        </Form.Item>

        <Form.Item label="API Key" tooltip="留空则不更新">
          <Input.Password
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="sk-..."
          />
        </Form.Item>

        <Form.Item label="模型名称">
          <Input
            value={settings.llm_model_name}
            onChange={(e) => setSettings({ ...settings, llm_model_name: e.target.value })}
            placeholder="qwen-max"
          />
        </Form.Item>

        <Form.Item label="启用混合检索" tooltip="BM25 关键词检索 + 向量语义检索，提升召回质量">
          <Switch
            checked={settings.hybrid_search}
            onChange={(v) => setSettings({ ...settings, hybrid_search: v })}
          />
        </Form.Item>

        <Form.Item label="启用重排序" tooltip="使用 bge-reranker-v2-m3 交叉编码器对检索结果重新排序，提升准确率">
          <Switch
            checked={settings.rerank_enabled}
            onChange={(v) => setSettings({ ...settings, rerank_enabled: v })}
          />
        </Form.Item>

        {settings.hybrid_search && (
          <>
            <Form.Item label="BM25 权重" tooltip="BM25 关键词检索的权重，向量权重 = 1 - BM25 权重">
              <Slider
                min={0}
                max={1}
                step={0.1}
                value={settings.bm25_weight}
                onChange={(v) => setSettings({ ...settings, bm25_weight: v })}
                marks={{ 0: '0', 0.5: '0.5', 1: '1' }}
              />
            </Form.Item>

            <Form.Item label="粗检索数量" tooltip="每路检索返回的候选数量">
              <InputNumber
                min={5}
                max={50}
                value={settings.retrieval_top_k}
                onChange={(v) => setSettings({ ...settings, retrieval_top_k: v || 20 })}
                style={{ width: '100%' }}
              />
            </Form.Item>
          </>
        )}

        <Form.Item label="最终返回数量" tooltip="返回给用户的检索结果数量">
          <Slider
            min={1}
            max={10}
            value={settings.rerank_top_k}
            onChange={(v) => setSettings({ ...settings, rerank_top_k: v })}
            marks={{ 1: '1', 5: '5', 10: '10' }}
          />
        </Form.Item>

        <Form.Item label="Temperature">
          <Slider
            min={0}
            max={1}
            step={0.1}
            value={settings.temperature}
            onChange={(v) => setSettings({ ...settings, temperature: v })}
            marks={{ 0: '0', 0.7: '0.7', 1: '1' }}
          />
        </Form.Item>

        <Form.Item label="最大生成长度">
          <InputNumber
            min={256}
            max={4096}
            step={256}
            value={settings.max_tokens}
            onChange={(v) => setSettings({ ...settings, max_tokens: v || 2048 })}
            style={{ width: '100%' }}
          />
        </Form.Item>

        <Form.Item label="上下文窗口大小" tooltip="模型的上下文窗口大小（token 数），影响历史消息保留量">
          <InputNumber
            min={2048}
            max={128000}
            step={1024}
            value={settings.context_window}
            onChange={(v) => setSettings({ ...settings, context_window: v || 8192 })}
            style={{ width: '100%' }}
          />
        </Form.Item>

        <Form.Item label="相似度阈值" tooltip="检索结果的最低相似度，越高越严格">
          <Slider
            min={0}
            max={1}
            step={0.05}
            value={settings.similarity_threshold}
            onChange={(v) => setSettings({ ...settings, similarity_threshold: v })}
            marks={{ 0: '0', 0.5: '0.5', 0.7: '0.7', 1: '1' }}
          />
        </Form.Item>

        <Form.Item>
          <Space>
            <Button type="primary" onClick={handleSave} loading={loading}>
              保存设置
            </Button>
          </Space>
        </Form.Item>
      </Form>

      <div style={{ marginTop: 8, padding: '8px 0' }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          支持所有 OpenAI 兼容 API：Qwen、DeepSeek、Moonshot、Ollama 等
        </Text>
      </div>
    </div>
  );
}
