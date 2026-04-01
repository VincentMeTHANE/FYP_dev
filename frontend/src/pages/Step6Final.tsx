import React, { useState, useCallback, useEffect } from 'react';
import { Card, Button, message, Spin, Space, Typography, Divider, Collapse, Tag, Tabs, Modal, Input, Alert } from 'antd';
import { PlayCircleOutlined, DownloadOutlined, CheckCircleOutlined, SyncOutlined, FilePdfOutlined } from '@ant-design/icons';
import MarkdownRenderer from '@/components/MarkdownRenderer';
import {
  getIntroduction,
  fetchFinalReportStream,
  fetchSummaryReportStream,
  getDownloadPdfUrl,
  getTaskIds,
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
}

interface Step6FinalProps {
  reportId: string;
  title: string;
  splitIds: string[];
  onBack?: () => void;
}

export const Step6Final: React.FC<Step6FinalProps> = ({ reportId, title, splitIds, onBack }) => {
  const [introduction, setIntroduction] = useState<string>('');
  const [introductionLoading, setIntroductionLoading] = useState(false);
  const [introductionComplete, setIntroductionComplete] = useState(false);

  const [chapters, setChapters] = useState<ChapterInfo[]>([]);
  const [chapterContents, setChapterContents] = useState<Record<string, FinalReportTask>>({});
  const [chaptersLoading, setChaptersLoading] = useState(false);
  const [allChaptersComplete, setAllChaptersComplete] = useState(false);

  const [summary, setSummary] = useState<string>('');
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryComplete, setSummaryComplete] = useState(false);

  const [requirement, setRequirement] = useState<string>('');
  const [showRequirementModal, setShowRequirementModal] = useState(false);
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    const loadChapters = async () => {
      const initialContents: Record<string, FinalReportTask> = {};
      // 直接使用传入的 splitIds 获取章节信息，不再调用 splitPlan（避免删除 serp_task 数据）
      for (const splitId of splitIds) {
        try {
          const tasks = await getTaskIds(splitId);
          if (tasks.length > 0) {
            // 使用第一个任务的 query 作为章节标题
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
      // 如果通过 getTaskIds 没有获取到章节信息，使用序号作为章节标题
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
      // 同时设置 chapters 状态
      setChapters(splitIds.map((splitId, index) => ({
        split_id: splitId,
        sectionTitle: initialContents[splitId]?.sectionTitle || `章节 ${index + 1}`
      })));
    };
    if (splitIds.length > 0) {
      loadChapters();
    }
  }, [splitIds]);

  const handleGenerateIntroduction = useCallback(async () => {
    setIntroductionLoading(true);
    try {
      const intro = await getIntroduction(reportId);
      setIntroduction(intro);
      setIntroductionComplete(true);
      message.success('引言生成完成');
    } catch {
      message.error('生成引言失败');
    } finally {
      setIntroductionLoading(false);
    }
  }, [reportId]);

  const handleGenerateChapter = useCallback(async (splitId: string) => {
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
            setChapterContents(prev => ({ ...prev, [splitId]: { ...prev[splitId], status: 'completed', content: fullContent } }));
            resolve();
          },
          (error) => {
            setChapterContents(prev => ({ ...prev, [splitId]: { ...prev[splitId], status: 'error', error: error.message } }));
            reject(error);
          }
        );
      });
    } catch { /* handled */ }
  }, [reportId, requirement]);

  const handleGenerateAllChapters = useCallback(async () => {
    setChaptersLoading(true);
    setGenerating(true);
    for (const chapter of chapters) {
      await handleGenerateChapter(chapter.split_id);
    }
    setChaptersLoading(false);
    setGenerating(false);
    setAllChaptersComplete(true);
    message.success('所有章节生成完成');
  }, [chapters, handleGenerateChapter]);

  const handleGenerateSummary = useCallback(async () => {
    setSummaryLoading(true);
    try {
      await new Promise<void>((resolve, reject) => {
        let fullContent = '';
        fetchSummaryReportStream(
          reportId,
          (chunk) => { fullContent = chunk; setSummary(chunk); },
          () => { setSummaryComplete(true); resolve(); },
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
