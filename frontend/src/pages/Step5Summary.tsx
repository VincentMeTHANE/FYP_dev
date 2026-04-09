import React, { useState, useCallback, useEffect } from 'react';
import { Card, Button, message, Space, Typography, Divider, Tag, Progress } from 'antd';
import { PlayCircleOutlined, RightOutlined, CheckCircleOutlined, SyncOutlined, ExclamationCircleOutlined, ClockCircleOutlined } from '@ant-design/icons';
import { fetchSummaryCompletion, getTaskIds } from '@/api';

const { Title, Text } = Typography;

interface SummaryTask {
  task_id: string;
  search_id: string;
  query: string;
  status: 'pending' | 'processing' | 'completed' | 'error';
  error?: string;
  executionTime?: number;
}

interface Step5SummaryProps {
  reportId: string;
  splitIds: string[];
  onNext: (reportId: string, executionTime?: number, tokenUsage?: { prompt: number; completion: number; total: number }) => void;
  onBack?: () => void;
}

export const Step5Summary: React.FC<Step5SummaryProps> = ({ reportId, splitIds, onNext, onBack }) => {
  const [tasks, setTasks] = useState<SummaryTask[]>([]);
  const [loading, setLoading] = useState(false);
  const [allComplete, setAllComplete] = useState(false);
  const [totalExecutionTime, setTotalExecutionTime] = useState<number>(0);

  // 格式化时间
  const formatTime = (seconds: number): string => {
    if (seconds < 60) {
      return `${seconds.toFixed(1)}秒`;
    } else {
      const minutes = Math.floor(seconds / 60);
      const remainingSeconds = (seconds % 60).toFixed(1);
      return `${minutes}分${remainingSeconds}秒`;
    }
  };

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
    if (tasks.length === 0) return;

    const startTime = Date.now();
    setLoading(true);
    setAllComplete(false);

    // 初始化所有任务状态为processing
    setTasks(prev => prev.map(t => ({ ...t, status: 'processing' as const, error: undefined })));

    // 并发请求所有summary任务
    const results = await Promise.all(
      tasks.map(async (task) => {
        const taskStartTime = Date.now();
        const result = await fetchSummaryCompletion(reportId, task.task_id, task.search_id);
        const elapsed = (Date.now() - taskStartTime) / 1000;
        return { taskId: task.task_id, result, executionTime: elapsed };
      })
    );

    // 更新所有任务的状态
    setTasks(prev => prev.map(task => {
      const resultItem = results.find(r => r.taskId === task.task_id);
      if (resultItem?.result.success) {
        return { ...task, status: 'completed' as const, executionTime: resultItem.executionTime };
      } else {
        return { ...task, status: 'error' as const, error: resultItem?.result.error || '未知错误', executionTime: resultItem?.executionTime };
      }
    }));

    setTotalExecutionTime((Date.now() - startTime) / 1000);

    // 检查是否有任何失败的任务
    const hasErrors = results.some(r => !r.result.success);
    if (hasErrors) {
      message.warning('部分搜索总结生成失败');
    } else {
      message.success('所有搜索总结已生成');
    }

    setLoading(false);

    // 检查是否全部完成（无失败）
    const allSucceeded = results.every(r => r.result.success);
    if (allSucceeded) {
      setAllComplete(true);
    }
  }, [tasks, reportId]);

  const completedCount = tasks.filter(t => t.status === 'completed').length;
  const errorCount = tasks.filter(t => t.status === 'error').length;
  const processingCount = tasks.filter(t => t.status === 'processing').length;
  const progressPercent = tasks.length > 0 ? Math.round((completedCount / tasks.length) * 100) : 0;

  const handleNext = useCallback(() => {
    onNext(reportId, totalExecutionTime);
  }, [reportId, onNext, totalExecutionTime]);

  return (
    <div style={{ padding: '24px' }}>
      <Card>
        <Title level={4}>第五步：生成搜索总结</Title>
        <Text type="secondary">为每个搜索任务生成总结（后台并发处理）</Text>
        <Divider />

        <Space style={{ marginBottom: '24px' }}>
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            onClick={handleGenerateSummaries}
            loading={loading}
            disabled={tasks.length === 0}
            size="large"
          >
            生成所有总结 ({tasks.length} 个)
          </Button>
          {allComplete && totalExecutionTime > 0 && (
            <Tag icon={<ClockCircleOutlined />} color="blue">
              总耗时: {formatTime(totalExecutionTime)}
            </Tag>
          )}
        </Space>

        {tasks.length > 0 && (
          <div style={{ marginBottom: '24px' }}>
            <Progress
              percent={progressPercent}
              status={errorCount > 0 ? 'exception' : allComplete ? 'success' : 'active'}
              format={() => `${completedCount} / ${tasks.length}`}
            />
            <div style={{ marginTop: '8px', display: 'flex', gap: '16px' }}>
              <Space>
                {processingCount > 0 && (
                  <Tag icon={<SyncOutlined spin />} color="processing">
                    处理中 ({processingCount})
                  </Tag>
                )}
                <Tag icon={<CheckCircleOutlined />} color="success">
                  已完成 ({completedCount})
                </Tag>
                {errorCount > 0 && (
                  <Tag icon={<ExclamationCircleOutlined />} color="error">
                    失败 ({errorCount})
                  </Tag>
                )}
              </Space>
            </div>
          </div>
        )}

        <div style={{ marginBottom: '24px' }}>
          <Text type="secondary" style={{ fontSize: '12px' }}>
            说明：所有搜索总结将在后台并发生成，无需等待单个任务完成。
            生成过程中不会展示具体的总结内容，仅显示进度状态。
          </Text>
        </div>

        {errorCount > 0 && (
          <div style={{ marginBottom: '24px', padding: '12px', backgroundColor: '#fff2f0', borderRadius: '4px' }}>
            <Text type="danger">
              有 {errorCount} 个任务失败，请检查网络或稍后重试。
            </Text>
          </div>
        )}

        <div style={{ marginTop: '24px', display: 'flex', justifyContent: 'space-between' }}>
          {onBack && <Button onClick={onBack}>上一步</Button>}
          <Button
            type="primary"
            size="large"
            icon={<RightOutlined />}
            onClick={handleNext}
            style={{ marginLeft: 'auto' }}
            disabled={!allComplete}
          >
            下一步：生成最终报告
          </Button>
        </div>
      </Card>
    </div>
  );
};

export default Step5Summary;
