import React, { useState, useCallback, useEffect } from 'react';
import { Card, Button, message, Spin, Space, Typography, Divider, Collapse, Tag } from 'antd';
import { PlayCircleOutlined, RightOutlined, CheckCircleOutlined, SyncOutlined } from '@ant-design/icons';
import MarkdownRenderer from '@/components/MarkdownRenderer';
import { fetchSummaryStream, getTaskIds } from '@/api';

const { Title, Text } = Typography;
const { Panel } = Collapse;

interface SummaryTask {
  task_id: string;
  search_id: string;
  query: string;
  summary: string;
  status: 'pending' | 'processing' | 'completed' | 'error';
  error?: string;
}

interface Step5SummaryProps {
  reportId: string;
  splitIds: string[];
  onNext: (reportId: string) => void;
  onBack?: () => void;
}

export const Step5Summary: React.FC<Step5SummaryProps> = ({ reportId, splitIds, onNext, onBack }) => {
  const [tasks, setTasks] = useState<SummaryTask[]>([]);
  const [loading, setLoading] = useState(false);
  const [allComplete, setAllComplete] = useState(false);
  const cancelRefs = useState<Record<string, () => void>>({})[0];

  useEffect(() => {
    const loadTasks = async () => {
      const allTasks: SummaryTask[] = [];
      for (const splitId of splitIds) {
        try {
          const taskIds = await getTaskIds(splitId);
          taskIds.forEach(task => {
            if (task.task_id) {
              allTasks.push({
                task_id: task.task_id,
                search_id: task.task_id,
                query: task.query || '',
                summary: '',
                status: 'pending'
              });
            }
          });
        } catch (error) {
          console.error('Error loading tasks:', error);
        }
      }
      setTasks(allTasks);
    };
    if (splitIds.length > 0) {
      loadTasks();
    }
  }, [splitIds]);

  const handleGenerateSummaries = useCallback(async () => {
    setLoading(true);
    for (let i = 0; i < tasks.length; i++) {
      const task = tasks[i];
      setTasks(prev => prev.map((t, idx) => idx === i ? { ...t, status: 'processing', error: undefined } : t));
      try {
        await new Promise<void>((resolve, reject) => {
          let fullContent = '';
          const cancel = fetchSummaryStream(
            reportId, task.task_id, task.search_id,
            (chunk) => {
              fullContent = chunk;
              setTasks(prev => prev.map((t, idx) => idx === i ? { ...t, summary: chunk } : t));
            },
            () => {
              setTasks(prev => prev.map((t, idx) => idx === i ? { ...t, status: 'completed', summary: fullContent } : t));
              resolve();
            },
            (error) => {
              setTasks(prev => prev.map((t, idx) => idx === i ? { ...t, status: 'error', error: error.message } : t));
              reject(error);
            }
          );
          cancelRefs[task.task_id] = cancel;
        });
      } catch { /* handled */ }
    }
    setLoading(false);
    setAllComplete(true);
    message.success('所有搜索总结已生成');
  }, [tasks, reportId, cancelRefs]);

  const handleCancel = useCallback(() => {
    Object.values(cancelRefs).forEach(cancel => cancel());
    setLoading(false);
    message.info('已取消生成');
  }, [cancelRefs]);

  const completedCount = tasks.filter(t => t.status === 'completed').length;
  const progressPercent = tasks.length > 0 ? Math.round((completedCount / tasks.length) * 100) : 0;

  return (
    <div style={{ padding: '24px' }}>
      <Card>
        <Title level={4}>第五步：生成搜索总结</Title>
        <Text type="secondary">为每个搜索任务生成流式总结</Text>
        <Divider />

        <Space style={{ marginBottom: '24px' }}>
          <Button type="primary" icon={<PlayCircleOutlined />} onClick={handleGenerateSummaries} loading={loading} disabled={tasks.length === 0} size="large">
            生成所有总结 ({tasks.length} 个)
          </Button>
          {loading && <Button danger onClick={handleCancel}>取消</Button>}
        </Space>

        {tasks.length > 0 && <div style={{ marginBottom: '24px' }}><Text type="secondary">进度：{completedCount} / {tasks.length} ({progressPercent}%)</Text></div>}

        <Collapse defaultActiveKey={[]} accordion>
          {tasks.map((task, index) => (
            <Panel
              key={`${task.task_id}-${index}`}
              header={
                <Space>
                  <span>Query {index + 1}</span>
                  <Text type="secondary" ellipsis style={{ maxWidth: '300px' }}>{task.query}</Text>
                  {task.status === 'processing' && <Tag icon={<SyncOutlined spin />} color="processing">生成中</Tag>}
                  {task.status === 'completed' && <Tag icon={<CheckCircleOutlined />} color="success">已完成</Tag>}
                  {task.status === 'error' && <Tag color="error">失败</Tag>}
                </Space>
              }
            >
              <div style={{ marginBottom: '16px' }}>
                <Text strong>查询内容：</Text>
                <div style={{ padding: '8px 12px', backgroundColor: '#f5f5f5', borderRadius: '4px', marginTop: '8px' }}><Text>{task.query}</Text></div>
              </div>
              <Divider>总结内容</Divider>
              {task.status === 'pending' && <Text type="secondary">等待生成...</Text>}
              {task.status === 'processing' && <div><Spin size="small" /> <Text type="secondary">正在生成...</Text>{task.summary && <div style={{ marginTop: '16px' }}><MarkdownRenderer content={task.summary} scrollToBottom={true} /></div>}</div>}
              {(task.status === 'completed' || task.status === 'error') && task.summary && <MarkdownRenderer content={task.summary} scrollToBottom={false} />}
              {task.status === 'error' && task.error && <Text type="danger" style={{ marginTop: '8px', display: 'block' }}>错误: {task.error}</Text>}
            </Panel>
          ))}
        </Collapse>

        <div style={{ marginTop: '24px', display: 'flex', justifyContent: 'space-between' }}>
          {onBack && <Button onClick={onBack}>上一步</Button>}
          <Button type="primary" size="large" icon={<RightOutlined />} onClick={() => onNext(reportId)} style={{ marginLeft: 'auto' }} disabled={!allComplete}>
            下一步：生成最终报告
          </Button>
        </div>
      </Card>
    </div>
  );
};

export default Step5Summary;
