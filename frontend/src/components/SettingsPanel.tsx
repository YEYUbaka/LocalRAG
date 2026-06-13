import { useState, useEffect } from 'react';
import { Form, Input, Slider, InputNumber, Button, message, Space, Typography } from 'antd';
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

        <Form.Item label="检索数量 (Top-K)">
          <Slider
            min={1}
            max={10}
            value={settings.top_k}
            onChange={(v) => setSettings({ ...settings, top_k: v })}
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
