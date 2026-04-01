import React from 'react';
import { Tag, Typography, Button, Tooltip } from 'antd';
import { DeleteOutlined, CopyOutlined, CheckOutlined } from '@ant-design/icons';

const { Text } = Typography;

interface JsonViewerProps {
  data: string | object | unknown[];
  onDelete?: (index: number) => void;
  deletable?: boolean;
  showIndex?: boolean;
}

export const JsonViewer: React.FC<JsonViewerProps> = ({
  data,
  onDelete,
  deletable = false,
  showIndex = true,
}) => {
  const [copiedIndex, setCopiedIndex] = React.useState<number | null>(null);

  const parsedData = React.useMemo(() => {
    if (typeof data === 'string') {
      try {
        const cleaned = data.replace(/```json\n?/g, '').replace(/\n?```/g, '').trim();
        return JSON.parse(cleaned);
      } catch {
        return null;
      }
    }
    return data;
  }, [data]);

  if (!parsedData || !Array.isArray(parsedData)) {
    return (
      <div style={{ padding: '16px', backgroundColor: '#f5f5f5', borderRadius: '8px' }}>
        <Text type="secondary">无法解析JSON数据</Text>
      </div>
    );
  }

  const handleCopy = async (text: string, index: number) => {
    await navigator.clipboard.writeText(text);
    setCopiedIndex(index);
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      {parsedData.map((item: { query: string; researchGoal?: string }, index: number) => (
        <div key={index} style={{ border: '1px solid #d9d9d9', borderRadius: '8px', padding: '16px', backgroundColor: '#fff', position: 'relative' }}>
          {showIndex && <Tag color="blue" style={{ position: 'absolute', top: '8px', right: deletable ? '50px' : '8px' }}>#{index + 1}</Tag>}
          <div style={{ marginBottom: '8px' }}>
            <Text strong style={{ color: '#1890ff' }}>query:</Text>
            <div style={{ marginTop: '4px', padding: '8px 12px', backgroundColor: '#f0f5ff', borderRadius: '4px', borderLeft: '3px solid #1890ff' }}>
              <Text style={{ fontFamily: 'monospace', wordBreak: 'break-all' }}>{item.query}</Text>
            </div>
          </div>
          {item.researchGoal && (
            <div style={{ marginBottom: '8px' }}>
              <Text strong style={{ color: '#52c41a' }}>researchGoal:</Text>
              <div style={{ marginTop: '4px', padding: '8px 12px', backgroundColor: '#f6ffed', borderRadius: '4px', borderLeft: '3px solid #52c41a' }}>
                <Text style={{ fontFamily: 'monospace', wordBreak: 'break-all' }}>{item.researchGoal}</Text>
              </div>
            </div>
          )}
          <div style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
            <Tooltip title={copiedIndex === index ? '已复制' : '复制JSON'}>
              <Button size="small" icon={copiedIndex === index ? <CheckOutlined /> : <CopyOutlined />} onClick={() => handleCopy(JSON.stringify(item, null, 2), index)}>
                {copiedIndex === index ? '已复制' : '复制'}
              </Button>
            </Tooltip>
            {deletable && onDelete && (
              <Tooltip title="删除此项">
                <Button size="small" danger icon={<DeleteOutlined />} onClick={() => onDelete(index)}>删除</Button>
              </Tooltip>
            )}
          </div>
        </div>
      ))}
    </div>
  );
};

export default JsonViewer;
