import React, { useState, useCallback, useEffect } from 'react';
import { Card, Button, message, Space, Typography, Divider, Progress, Table, Tag, Switch, Tooltip } from 'antd';
import { PlayCircleOutlined, RightOutlined, CheckCircleOutlined, SyncOutlined, QuestionCircleOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { executeSearch, getTaskIds } from '@/api';

const { Title, Text } = Typography;

interface SearchTask {
  task_id: string;
  query: string;
  researchGoal: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  error?: string;
}

interface Step4SearchProps {
  reportId: string;
  splitIds: string[];
  onNext: (reportId: string) => void;
  onBack?: () => void;
}

export const Step4Search: React.FC<Step4SearchProps> = ({ reportId, splitIds, onNext, onBack }) => {
  const [tasks, setTasks] = useState<SearchTask[]>([]);
  const [loading, setLoading] = useState(false);
  const [allComplete, setAllComplete] = useState(false);
  const [useRag, setUseRag] = useState(true);

  useEffect(() => {
    const loadTasks = async () => {
      const allTasks: SearchTask[] = [];
      for (const splitId of splitIds) {
        try {
          const taskIds = await getTaskIds(splitId);
          taskIds.forEach((task, idx) => {
            if (task.task_id) {
              allTasks.push({
                task_id: task.task_id,
                query: task.query || '',
                researchGoal: task.researchGoal || '',
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

  const handleSearch = useCallback(async () => {
    setLoading(true);
    const searchPromises = tasks.map(async (task, index) => {
      setTasks(prev => prev.map((t, i) => i === index ? { ...t, status: 'processing' } : t));
      try {
        await executeSearch({ task_id: task.task_id, max_results: 10, include_images: true, use_rag: useRag });
        setTasks(prev => prev.map((t, i) => i === index ? { ...t, status: 'completed' } : t));
      } catch {
        setTasks(prev => prev.map((t, i) => i === index ? { ...t, status: 'failed' } : t));
      }
    });
    await Promise.all(searchPromises);
    setLoading(false);
    setAllComplete(true);
    message.success('所有搜索任务已完成');
  }, [tasks, useRag]);

  const handleRetryFailed = useCallback(async () => {
    const failedTasks = tasks.filter(t => t.status === 'failed');
    if (failedTasks.length === 0) {
      message.info('没有失败的任务');
      return;
    }
    setLoading(true);
    for (let i = 0; i < tasks.length; i++) {
      if (tasks[i].status === 'failed') {
        setTasks(prev => prev.map((t, idx) => idx === i ? { ...t, status: 'processing', error: undefined } : t));
        try {
          await executeSearch({ task_id: tasks[i].task_id, max_results: 10, include_images: true, use_rag: useRag });
          setTasks(prev => prev.map((t, idx) => idx === i ? { ...t, status: 'completed' } : t));
        } catch {
          setTasks(prev => prev.map((t, idx) => idx === i ? { ...t, status: 'failed' } : t));
        }
      }
    }
    setLoading(false);
    const allSucceeded = tasks.every(t => t.status === 'completed');
    if (allSucceeded) {
      setAllComplete(true);
      message.success('所有搜索任务已完成');
    }
  }, [tasks, useRag]);

  const columns: ColumnsType<SearchTask> = [
    { title: '序号', dataIndex: 'index', key: 'index', width: 60, render: (_, __, index) => index + 1 },
    { title: '查询内容 (query)', dataIndex: 'query', key: 'query', ellipsis: true },
    { title: '研究目标 (researchGoal)', dataIndex: 'researchGoal', key: 'researchGoal', ellipsis: true },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 120,
      render: (status: SearchTask['status']) => {
        switch (status) {
          case 'pending': return <Tag>等待中</Tag>;
          case 'processing': return <Tag icon={<SyncOutlined spin />} color="processing">进行中</Tag>;
          case 'completed': return <Tag icon={<CheckCircleOutlined />} color="success">已完成</Tag>;
          case 'failed': return <Tag color="error">失败</Tag>;
          default: return <Tag>未知</Tag>;
        }
      }
    },
  ];

  const completedCount = tasks.filter(t => t.status === 'completed').length;
  const progressPercent = tasks.length > 0 ? Math.round((completedCount / tasks.length) * 100) : 0;

  return (
    <div style={{ padding: '24px' }}>
      <Card>
        <Title level={4}>第四步：执行搜索</Title>
        <Text type="secondary">并发执行所有搜索任务获取相关信息</Text>
        <Divider />

        <Space style={{ marginBottom: '24px' }} wrap>
          <Button type="primary" icon={<PlayCircleOutlined />} onClick={handleSearch} loading={loading} disabled={tasks.length === 0} size="large">
            开始执行搜索 ({tasks.length} 个任务)
          </Button>
          {tasks.some(t => t.status === 'failed') && (
            <Button icon={<SyncOutlined />} onClick={handleRetryFailed} loading={loading}>重试失败任务</Button>
          )}
          <Divider type="vertical" style={{ height: '100%' }} />
          <Space>
            <Switch checked={useRag} onChange={setUseRag} disabled={loading} />
            <Text>
              使用 RAG 增强搜索
              <Tooltip title="开启后，搜索时会结合本地知识库进行增强检索，提高搜索结果的相关性">
                <QuestionCircleOutlined style={{ marginLeft: 4 }} />
              </Tooltip>
            </Text>
          </Space>
        </Space>

        {tasks.length > 0 && (
          <div style={{ marginBottom: '24px' }}>
            <Text type="secondary">进度：{completedCount} / {tasks.length} ({progressPercent}%)</Text>
            <Progress percent={progressPercent} status={allComplete ? 'success' : 'active'} style={{ marginTop: '8px' }} />
          </div>
        )}

        <Table columns={columns} dataSource={tasks} rowKey={(record, index) => `${record.task_id}-${index}`} pagination={false} size="small" scroll={{ y: 400 }} />

        <div style={{ marginTop: '24px', display: 'flex', justifyContent: 'space-between' }}>
          {onBack && <Button onClick={onBack}>上一步</Button>}
          <Button type="primary" size="large" icon={<RightOutlined />} onClick={() => onNext(reportId)} style={{ marginLeft: 'auto' }} disabled={!allComplete}>
            下一步：生成搜索总结
          </Button>
        </div>
      </Card>
    </div>
  );
};

export default Step4Search;
