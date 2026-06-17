import { useState, useEffect } from 'react';
import { Form, Input, Slider, InputNumber, Button, message, Space, Typography, Switch, Select, Divider, Tag } from 'antd';
import type { Settings } from '../types';
import { getSettings, updateSettings } from '../services/api';

const { Text } = Typography;
const { Option } = Select;

// LLM 预设配置
interface LLMPreset {
  name: string;
  base_url: string;
  models: { label: string; value: string; description?: string }[];
  description?: string;
  useEndpointId?: boolean; // 是否需要使用接入点 ID
}

const LLM_PRESETS: LLMPreset[] = [
  {
    name: '通义千问',
    base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    models: [
      { label: 'qwen-max', value: 'qwen-max', description: '旗舰模型，能力最强' },
      { label: 'qwen-plus', value: 'qwen-plus', description: '均衡性能，性价比高' },
      { label: 'qwen-turbo', value: 'qwen-turbo', description: '速度快，成本低' },
      { label: 'qwen-long', value: 'qwen-long', description: '支持超长文本' },
    ],
    description: '阿里云百炼平台',
  },
  {
    name: '火山方舟（豆包）',
    base_url: 'https://ark.cn-beijing.volces.com/api/v3',
    models: [
      // 文本生成模型
      { label: 'doubao-pro-32k (接入点)', value: 'ep-xxxx', description: '旗舰模型，32k 上下文，能力最强' },
      { label: 'doubao-pro-128k (接入点)', value: 'ep-xxxx', description: '旗舰模型，128k 长上下文' },
      { label: 'doubao-lite-32k (接入点)', value: 'ep-xxxx', description: '轻量模型，32k 上下文，速度快成本低' },
      { label: 'doubao-lite-128k (接入点)', value: 'ep-xxxx', description: '轻量模型，128k 长上下文' },
      // 视觉模型
      { label: 'doubao-vision-pro-32k (接入点)', value: 'ep-xxxx', description: '视觉旗舰，支持图片理解' },
      { label: 'doubao-vision-lite-32k (接入点)', value: 'ep-xxxx', description: '视觉轻量，图片理解速度快' },
      // 深度思考模型
      { label: 'doubao-1.5-pro-32k (接入点)', value: 'ep-xxxx', description: '深度思考模型，推理能力强' },
      { label: 'doubao-1.5-pro-256k (接入点)', value: 'ep-xxxx', description: '深度思考 + 超长上下文' },
      // 火山方舟托管的第三方模型
      { label: 'deepseek-r1 (接入点)', value: 'ep-xxxx', description: '火山方舟托管 DeepSeek-R1 深度思考' },
      { label: 'deepseek-v3 (接入点)', value: 'ep-xxxx', description: '火山方舟托管 DeepSeek-V3 通用模型' },
    ],
    description: '字节跳动火山引擎（需创建接入点）',
    useEndpointId: true,
  },
  {
    name: 'DeepSeek',
    base_url: 'https://api.deepseek.com/v1',
    models: [
      { label: 'deepseek-chat', value: 'deepseek-chat', description: '通用对话模型' },
      { label: 'deepseek-reasoner', value: 'deepseek-reasoner', description: '深度推理模型' },
    ],
    description: 'DeepSeek 官方 API',
  },
  {
    name: 'Moonshot (Kimi)',
    base_url: 'https://api.moonshot.cn/v1',
    models: [
      { label: 'moonshot-v1-8k', value: 'moonshot-v1-8k', description: '8k 上下文' },
      { label: 'moonshot-v1-32k', value: 'moonshot-v1-32k', description: '32k 上下文' },
      { label: 'moonshot-v1-128k', value: 'moonshot-v1-128k', description: '128k 长上下文' },
    ],
    description: '月之暗面 Kimi',
  },
  {
    name: 'Ollama (本地)',
    base_url: 'http://localhost:11434/v1',
    models: [
      { label: 'qwen2.5:7b', value: 'qwen2.5:7b', description: '7B 参数，适合轻量任务' },
      { label: 'qwen2.5:14b', value: 'qwen2.5:14b', description: '14B 参数，性能均衡' },
      { label: 'llama3.1:8b', value: 'llama3.1:8b', description: 'Meta Llama 3.1 8B' },
      { label: 'glm4:9b', value: 'glm4:9b', description: '智谱 GLM-4 9B' },
    ],
    description: '本地 Ollama 服务',
  },
];

export default function SettingsPanel() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [apiKey, setApiKey] = useState('');
  const [loading, setLoading] = useState(false);
  const [selectedPreset, setSelectedPreset] = useState<string>('');

  useEffect(() => {
    getSettings()
      .then(setSettings)
      .catch((e) => message.error('加载设置失败: ' + e.message));
  }, []);

  const applyPreset = (presetName: string) => {
    const preset = LLM_PRESETS.find(p => p.name === presetName);
    if (preset && settings) {
      setSelectedPreset(presetName);
      setSettings({
        ...settings,
        llm_base_url: preset.base_url,
        llm_model_name: preset.models[0].value,
      });
    }
  };

  const getCurrentPreset = (): LLMPreset | undefined => {
    return LLM_PRESETS.find(p => p.base_url === settings?.llm_base_url);
  };

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
        rerank_threshold: settings.rerank_threshold,
        query_rewrite_enabled: settings.query_rewrite_enabled,
        web_search_enabled: settings.web_search_enabled,
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
        <Form.Item label="快速配置" tooltip="选择预设自动填充 API 地址和模型">
          <Select
            placeholder="选择 LLM 服务商预设..."
            value={selectedPreset || undefined}
            onChange={applyPreset}
            allowClear
          >
            {LLM_PRESETS.map(preset => (
              <Option key={preset.name} value={preset.name}>
                {preset.name} {preset.description && <Text type="secondary">({preset.description})</Text>}
              </Option>
            ))}
          </Select>
        </Form.Item>

        <Divider style={{ margin: '12px 0' }} />

        <Form.Item
          label="Base URL"
          tooltip="OpenAI 兼容 API 地址"
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
            autoComplete="new-password"
          />
        </Form.Item>

        <Form.Item label="模型名称" tooltip={getCurrentPreset()?.useEndpointId ? '火山方舟需要填写接入点 ID（如 ep-20240xxx），不是模型名称' : undefined}>
          {getCurrentPreset()?.useEndpointId ? (
            // 火山方舟需要手动输入接入点 ID
            <div>
              <Input
                value={settings.llm_model_name}
                onChange={(e) => setSettings({ ...settings, llm_model_name: e.target.value })}
                placeholder="输入接入点 ID（如 ep-20240xxxxxxxxx）"
                style={{ marginBottom: 8 }}
              />
              <div style={{ padding: '8px 12px', background: '#fffbe6', borderRadius: 6, border: '1px solid #ffe58f' }}>
                <Text style={{ fontSize: 12 }}>
                  <strong>⚠️ 重要：请填写接入点 ID，不是模型名称！</strong><br />
                  1. 前往 <a href="https://console.volcengine.com/ark" target="_blank" rel="noopener">火山引擎控制台</a><br />
                  2. 进入「模型推理」→「接入点管理」<br />
                  3. 创建接入点，复制接入点 ID（格式：ep-20240xxxxxxxxx）<br />
                  4. 将接入点 ID 粘贴到上方输入框
                </Text>
              </div>
              <div style={{ marginTop: 8 }}>
                <Text type="secondary" style={{ fontSize: 11 }}>可选模型参考：</Text>
                <div style={{ marginTop: 4, display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                  {getCurrentPreset()?.models.map(model => (
                    <Tag
                      key={model.value}
                      style={{ cursor: 'pointer', fontSize: 11 }}
                      onClick={() => {
                        // 提示用户需要替换为实际的接入点 ID
                        message.info(`请将 "${model.label}" 替换为您在控制台创建的实际接入点 ID`);
                      }}
                    >
                      {model.label}
                    </Tag>
                  ))}
                </div>
              </div>
            </div>
          ) : getCurrentPreset() ? (
            <Select
              value={settings.llm_model_name}
              onChange={(v) => setSettings({ ...settings, llm_model_name: v })}
              showSearch
              allowClear
              placeholder="选择模型..."
              optionLabelProp="label"
            >
              {getCurrentPreset()?.models.map(model => (
                <Option key={model.value} value={model.value} label={model.label}>
                  <div>
                    <div>{model.label}</div>
                    {model.description && (
                      <Text type="secondary" style={{ fontSize: 11 }}>{model.description}</Text>
                    )}
                  </div>
                </Option>
              ))}
            </Select>
          ) : (
            <Input
              value={settings.llm_model_name}
              onChange={(e) => setSettings({ ...settings, llm_model_name: e.target.value })}
              placeholder="qwen-max"
            />
          )}
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

        {settings.rerank_enabled && (
          <Form.Item label="重排序阈值" tooltip="重排序分数低于此值的结果将被过滤，越高越严格（推荐 1.0）">
            <Slider
              min={0}
              max={3}
              step={0.1}
              value={settings.rerank_threshold}
              onChange={(v) => setSettings({ ...settings, rerank_threshold: v })}
              marks={{ 0: '0', 1: '1', 2: '2', 3: '3' }}
            />
          </Form.Item>
        )}

        <Form.Item label="启用查询改写" tooltip="使用 LLM 将问题改写为多个不同表述，扩大检索召回范围">
          <Switch
            checked={settings.query_rewrite_enabled}
            onChange={(v) => setSettings({ ...settings, query_rewrite_enabled: v })}
          />
        </Form.Item>

        <Form.Item
          label="启用联网搜索"
          tooltip="当知识库无匹配结果时，自动联网搜索补充信息（查询将发送至 DuckDuckGo）"
        >
          <Switch
            checked={settings.web_search_enabled}
            onChange={(v) => setSettings({ ...settings, web_search_enabled: v })}
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
          支持所有 OpenAI 兼容 API：Qwen、豆包、DeepSeek、Moonshot、Ollama 等
        </Text>
      </div>
    </div>
  );
}
