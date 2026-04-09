import React, { useState, useCallback, useEffect } from 'react';
import { Card, Button, message, Spin, Space, Typography, Divider, Collapse, Tag, Tabs, Modal, Input, Alert } from 'antd';
import { PlayCircleOutlined, DownloadOutlined, CheckCircleOutlined, SyncOutlined, FilePdfOutlined, ClockCircleOutlined } from '@ant-design/icons';
import MarkdownRenderer from '@/components/MarkdownRenderer';
import FinalStats from '@/components/FinalStats';
import {
  getIntroduction,
  fetchFinalReportStream,
  fetchSummaryReportStream,
  getDownloadPdfUrl,
  getTaskIds,
  getTokenStats,
} from '@/api';
import type { ChapterInfo } from '@/types';

const { Title, Text } = Typography;
const { Panel } = Collapse;
const { TextArea } = Input;

interface FinalReportTask {
  split_id: string;
  sectionTitle: string;
  content: string;
  status: 'pending' | 'processing' | 'completed' | 'error';
  error?: string;
  executionTime?: number;
}

interface Step6FinalProps {
  reportId: string;
  title: string;
  splitIds: string[];
  onBack?: () => void;
  // 从App.tsx传入的累计统计
  totalExecutionTime?: number;
  totalPromptTokens?: number;
  totalCompletionTokens?: number;
  totalTokens?: number;
  stepTimes?: Record<string, number>;
}

export const Step6Final: React.FC<Step6FinalProps> = ({
  reportId,
  title,
  splitIds,
  onBack,
  totalExecutionTime = 0,
  totalPromptTokens = 0,
  totalCompletionTokens = 0,
  totalTokens = 0,
  stepTimes = {}
}) => {
  const [introduction, setIntroduction] = useState<string>('');
  const [introductionLoading, setIntroductionLoading] = useState(false);
  const [introductionComplete, setIntroductionComplete] = useState(false);
  const [introductionTime, setIntroductionTime] = useState<number>(0);

  const [chapters, setChapters] = useState<ChapterInfo[]>([]);
  const [chapterContents, setChapterContents] = useState<Record<string, FinalReportTask>>({});
  const [chaptersLoading, setChaptersLoading] = useState(false);
  const [allChaptersComplete, setAllChaptersComplete] = useState(false);
  const [totalChaptersTime, setTotalChaptersTime] = useState<number>(0);

  const [summary, setSummary] = useState<string>('');
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryComplete, setSummaryComplete] = useState(false);
  const [summaryTime, setSummaryTime] = useState<number>(0);

  const [requirement, setRequirement] = useState<string>('');
  const [showRequirementModal, setShowRequirementModal] = useState(false);
  const [generating, setGenerating] = useState(false);

  // Token统计
  const [tokenStats, setTokenStats] = useState<any>(null);

  // 格式化时间
  const formatTime = (seconds: number): string => {
    if (seconds < 60) {
      return `${seconds.toFixed(1)}秒`;
    } else if (seconds < 3600) {
      const minutes = Math.floor(seconds / 60);
      const remainingSeconds = (seconds % 60).toFixed(0);
      return `${minutes}分${remainingSeconds}秒`;
    } else {
      const hours = Math.floor(seconds / 3600);
      const minutes = Math.floor((seconds % 3600) / 60);
      return `${hours}小时${minutes}分`;
    }
  };

  // 计算总耗时
  const overallExecutionTime = totalExecutionTime + introductionTime + totalChaptersTime + summaryTime;

  // 加载Token统计
  const loadTokenStats = useCallback(async () => {
    try {
      const stats = await getTokenStats(reportId);
      setTokenStats(stats);
    } catch (error) {
      console.error('Failed to load token stats:', error);
    }
  }, [reportId]);

  useEffect(() => {
    const loadChapters = async () => {
      const initialContents: Record<string, FinalReportTask> = {};
      for (const splitId of splitIds) {
        try {
          const tasks = await getTaskIds(splitId);
          if (tasks.length > 0) {
            initialContents[splitId] = {
              split_id: splitId,
              sectionTitle: tasks[0].researchGoal || `章节 ${Object.keys(initialContents).length + 1}`,
              content: '',
              status: 'pending'
            };
          }
        } catch (error) {
          console.error('Error loading tasks for splitId:', splitId, error);
        }
      }
      if (Object.keys(initialContents).length === 0) {
        splitIds.forEach((splitId, index) => {
          initialContents[splitId] = {
            split_id: splitId,
            sectionTitle: `章节 ${index + 1}`,
            content: '',
            status: 'pending'
          };
        });
      }
      setChapterContents(initialContents);
      setChapters(splitIds.map((splitId, index) => ({
        split_id: splitId,
        sectionTitle: initialContents[splitId]?.sectionTitle || `章节 ${index + 1}`
      })));
    };
    if (splitIds.length > 0) {
      loadChapters();
      loadTokenStats();
    }
  }, [splitIds, loadTokenStats]);

  const handleGenerateIntroduction = useCallback(async () => {
    const startTime = Date.now();
    setIntroductionLoading(true);
    try {
      const intro = await getIntroduction(reportId);
      setIntroduction(intro);
      setIntroductionComplete(true);
      setIntroductionTime((Date.now() - startTime) / 1000);
      message.success('引言生成完成');
    } catch {
      message.error('生成引言失败');
    } finally {
      setIntroductionLoading(false);
    }
  }, [reportId]);

  const handleGenerateChapter = useCallback(async (splitId: string) => {
    const startTime = Date.now();
    setChapterContents(prev => ({ ...prev, [splitId]: { ...prev[splitId], status: 'processing', error: undefined } }));
    try {
      await new Promise<void>((resolve, reject) => {
        let fullContent = '';
        const cancel = fetchFinalReportStream(
          reportId, splitId, requirement,
          (chunk) => {
            fullContent = chunk;
            setChapterContents(prev => ({ ...prev, [splitId]: { ...prev[splitId], content: chunk } }));
          },
          () => {
            const elapsed = (Date.now() - startTime) / 1000;
            setChapterContents(prev => ({ ...prev, [splitId]: { ...prev[splitId], status: 'completed', content: fullContent, executionTime: elapsed } }));
            resolve();
          },
          (error) => {
            const elapsed = (Date.now() - startTime) / 1000;
            setChapterContents(prev => ({ ...prev, [splitId]: { ...prev[splitId], status: 'error', error: error.message, executionTime: elapsed } }));
            reject(error);
          }
        );
      });
    } catch { /* handled */ }
  }, [reportId, requirement]);

  const handleGenerateAllChapters = useCallback(async () => {
    const startTime = Date.now();
    setChaptersLoading(true);
    setGenerating(true);
    for (const chapter of chapters) {
      await handleGenerateChapter(chapter.split_id);
    }
    setTotalChaptersTime((Date.now() - startTime) / 1000);
    setChaptersLoading(false);
    setGenerating(false);
    setAllChaptersComplete(true);
    loadTokenStats(); // 重新加载token统计
    message.success('所有章节生成完成');
  }, [chapters, handleGenerateChapter, loadTokenStats]);

  const handleGenerateSummary = useCallback(async () => {
    const startTime = Date.now();
    setSummaryLoading(true);
    try {
      await new Promise<void>((resolve, reject) => {
        let fullContent = '';
        fetchSummaryReportStream(
          reportId,
          (chunk) => { fullContent = chunk; setSummary(chunk); },
          () => {
            setSummaryComplete(true);
            setSummaryTime((Date.now() - startTime) / 1000);
            resolve();
          },
          (error) => { message.error('生成总结失败: ' + error.message); reject(error); }
        );
      });
    } catch { /* handled */ } finally {
      setSummaryLoading(false);
    }
  }, [reportId]);

  const handleDownloadPdf = useCallback(() => {
    const url = getDownloadPdfUrl(reportId);
    window.open(url, '_blank');
    message.success('开始下载PDF');
  }, [reportId]);

  const completedChapters = Object.values(chapterContents).filter(c => c.status === 'completed').length;
  const progressPercent = chapters.length > 0 ? Math.round((completedChapters / chapters.length) * 100) : 0;

  return (
    <div style={{ padding: '24px' }}>
      <Card>
        <Title level={4}>第六步：生成最终报告</Title>
        <Card size="small" style={{ marginBottom: '24px', backgroundColor: '#f0f5ff' }}>
          <Text strong>报告主题：</Text><Text>{title}</Text>
        </Card>
        <Divider />

        <Tabs defaultActiveKey="1" items={[
          {
            key: '1', label: '1. 引言', children: (
              <Card size="small">
                <Space style={{ marginBottom: '16px' }}>
                  <Button type="primary" icon={<PlayCircleOutlined />} onClick={handleGenerateIntroduction} loading={introductionLoading} disabled={introductionComplete}>
                    {introductionComplete ? '重新生成引言' : '生成引言'}
                  </Button>
                  {introductionLoading && <Spin />}
                  {introductionComplete && introductionTime > 0 && (
                    <Tag icon={<ClockCircleOutlined />}>{formatTime(introductionTime)}</Tag>
                  )}
                </Space>
                {introductionComplete ? <MarkdownRenderer content={introduction} scrollToBottom={true} /> : <Text type="secondary">点击上方按钮生成引言</Text>}
              </Card>
            )
          },
          {
            key: '2', label: '2. 正文', children: (
              <Card size="small">
                <Space style={{ marginBottom: '16px' }}>
                  <Button type="primary" icon={<PlayCircleOutlined />} onClick={() => setShowRequirementModal(true)} disabled={generating}>
                    {generating ? '生成中...' : '开始生成正文'}
                  </Button>
                  {generating && <Spin />}
                  <Text type="secondary">进度：{completedChapters} / {chapters.length} ({progressPercent}%)</Text>
                  {allChaptersComplete && totalChaptersTime > 0 && (
                    <Tag icon={<ClockCircleOutlined />}>{formatTime(totalChaptersTime)}</Tag>
                  )}
                </Space>
                <Collapse>
                  {chapters.map((chapter, index) => {
                    const chapterData = chapterContents[chapter.split_id];
                    if (!chapterData) return null;
                    return (
                      <Panel key={chapter.split_id} header={<Space><span>第 {index + 1} 章：{chapter.sectionTitle}</span>
                        {chapterData.status === 'processing' && <Tag icon={<SyncOutlined spin />} color="processing">生成中</Tag>}
                        {chapterData.status === 'completed' && <Tag icon={<CheckCircleOutlined />} color="success">已完成</Tag>}
                        {chapterData.status === 'error' && <Tag color="error">失败</Tag>}
                        {chapterData.executionTime && <Tag icon={<ClockCircleOutlined />}>{formatTime(chapterData.executionTime)}</Tag>}
                      </Space>}>
                        {chapterData.status === 'pending' && <Button size="small" onClick={() => handleGenerateChapter(chapter.split_id)}>生成此章节</Button>}
                        {(chapterData.status === 'processing' || chapterData.status === 'completed') && chapterData.content && <MarkdownRenderer content={chapterData.content} scrollToBottom={true} />}
                        {chapterData.status === 'error' && <Alert type="error" message={chapterData.error} />}
                      </Panel>
                    );
                  })}
                </Collapse>
              </Card>
            )
          },
          {
            key: '3', label: '3. 总结', children: (
              <Card size="small">
                <Space style={{ marginBottom: '16px' }}>
                  <Button type="primary" icon={<PlayCircleOutlined />} onClick={handleGenerateSummary} loading={summaryLoading} disabled={summaryComplete}>
                    {summaryComplete ? '重新生成总结' : '生成总结'}
                  </Button>
                  {summaryLoading && <Spin />}
                  {summaryComplete && summaryTime > 0 && (
                    <Tag icon={<ClockCircleOutlined />}>{formatTime(summaryTime)}</Tag>
                  )}
                </Space>
                {summaryComplete ? <MarkdownRenderer content={summary} scrollToBottom={true} /> : <Text type="secondary">点击上方按钮生成总结</Text>}
              </Card>
            )
          },
          {
            key: '4', label: '4. 下载', children: (
              <Card size="small">
                <Space direction="vertical" size="large" style={{ width: '100%' }}>
                  <Alert message="报告下载" description="报告生成完成后，您可以下载PDF或Word格式的报告" type="info" />
                  <Space>
                    <Button type="primary" icon={<DownloadOutlined />} onClick={handleDownloadPdf} disabled={!allChaptersComplete || !introductionComplete || !summaryComplete} size="large">
                      下载PDF报告
                    </Button>
                    <Button icon={<FilePdfOutlined />} disabled={!allChaptersComplete || !introductionComplete || !summaryComplete} size="large">
                      下载Word报告
                    </Button>
                  </Space>
                  {(!allChaptersComplete || !introductionComplete || !summaryComplete) && <Text type="secondary">请先完成引言、正文和总结的生成后再下载</Text>}
                </Space>
              </Card>
            )
          }
        ]} />

        <div style={{ marginTop: '24px' }}>
          {onBack && <Button onClick={onBack}>返回上一步</Button>}
        </div>
      </Card>

      {/* 最终统计信息 */}
      <FinalStats
        totalExecutionTime={overallExecutionTime}
        totalPromptTokens={tokenStats?.total_prompt_tokens || totalPromptTokens}
        totalCompletionTokens={tokenStats?.total_completion_tokens || totalCompletionTokens}
        totalTokens={tokenStats?.total_tokens || totalTokens}
        stepTimes={stepTimes}
        tokenStats={tokenStats?.step_stats}
      />

      <Modal title="设置书写要求" open={showRequirementModal}
        onOk={() => { setShowRequirementModal(false); handleGenerateAllChapters(); }}
        onCancel={() => setShowRequirementModal(false)} okText="开始生成" cancelText="取消">
        <Text type="secondary" style={{ marginBottom: '16px', display: 'block' }}>您可以设置报告的书写要求，例如：语言风格、内容重点等。留空则使用默认要求。</Text>
        <TextArea placeholder="请输入书写要求（可选）" value={requirement} onChange={(e) => setRequirement(e.target.value)} rows={4} />
      </Modal>
    </div>
  );
};

export default Step6Final;
