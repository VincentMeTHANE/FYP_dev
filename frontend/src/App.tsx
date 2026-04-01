import React, { useState, useCallback } from 'react';
import { ConfigProvider, Layout, Typography, Button, Card, Space, message, App as AntApp } from 'antd';
import { PlusOutlined, HistoryOutlined } from '@ant-design/icons';
import zhCN from 'antd/locale/zh_CN';
import StepProgress from '@/components/StepProgress';
import Step1Questions from '@/pages/Step1Questions';
import Step2Plan from '@/pages/Step2Plan';
import Step3Serp from '@/pages/Step3Serp';
import Step4Search from '@/pages/Step4Search';
import Step5Summary from '@/pages/Step5Summary';
import Step6Final from '@/pages/Step6Final';
import { createReport } from '@/api';
import type { ChapterInfo } from '@/types';

const { Header, Content, Footer } = Layout;
const { Title, Text } = Typography;

const App: React.FC = () => {
  const [currentStep, setCurrentStep] = useState(1);
  const [reportId, setReportId] = useState<string | null>(null);
  const [title, setTitle] = useState<string>('');
  const [chapters, setChapters] = useState<ChapterInfo[]>([]);
  const [splitIds, setSplitIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  const handleCreateReport = useCallback(async () => {
    setLoading(true);
    try {
      const newReportId = await createReport();
      setReportId(newReportId);
      setCurrentStep(1);
      message.success('报告创建成功');
    } catch {
      message.error('创建报告失败');
    } finally {
      setLoading(false);
    }
  }, []);

  const handleStep1Next = useCallback((newReportId: string, questions: string) => {
    setReportId(newReportId);
    const firstLine = questions.split('\n')[0] || '';
    const extractedTitle = firstLine.replace(/^\d+[\.、]\s*/, '').trim();
    setTitle(extractedTitle || '研究报告');
    setCurrentStep(2);
  }, []);

  const handleStep2Next = useCallback((newReportId: string, newChapters: ChapterInfo[]) => {
    setReportId(newReportId);
    setChapters(newChapters);
    setSplitIds(newChapters.map(c => c.split_id));
    setCurrentStep(3);
  }, []);

  const handleStep3Next = useCallback((newReportId: string) => {
    setReportId(newReportId);
    setCurrentStep(4);
  }, []);

  const handleStep4Next = useCallback((newReportId: string) => {
    setReportId(newReportId);
    setCurrentStep(5);
  }, []);

  const handleStep5Next = useCallback((newReportId: string) => {
    setReportId(newReportId);
    setCurrentStep(6);
  }, []);

  const handleStepChange = useCallback((step: number) => {
    if (step < currentStep) {
      setCurrentStep(step);
    }
  }, [currentStep]);

  const renderStartPage = () => (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '60vh' }}>
      <Card style={{ textAlign: 'center', padding: '40px', maxWidth: '500px' }}>
        <Title level={2}>深度研究报告生成系统</Title>
        <Text type="secondary" style={{ display: 'block', marginBottom: '32px' }}>
          基于AI的自动化深度研究报告生成工具，只需输入主题，即可完成从问题询问到报告生成的完整流程。
        </Text>
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <Button
            type="primary"
            size="large"
            icon={<PlusOutlined />}
            onClick={handleCreateReport}
            loading={loading}
            style={{ width: '100%', height: '56px' }}
          >
            创建新报告
          </Button>
          <Button
            size="large"
            icon={<HistoryOutlined />}
            onClick={() => message.info('历史报告功能开发中')}
            style={{ width: '100%' }}
          >
            查看历史报告
          </Button>
        </Space>
      </Card>
    </div>
  );

  const renderStepContent = () => {
    if (!reportId) {
      return renderStartPage();
    }

    switch (currentStep) {
      case 1:
        return <Step1Questions reportId={reportId} onNext={handleStep1Next} />;
      case 2:
        return <Step2Plan reportId={reportId} title={title} onNext={handleStep2Next} onBack={() => setCurrentStep(1)} />;
      case 3:
        return <Step3Serp reportId={reportId} chapters={chapters} onNext={handleStep3Next} onBack={() => setCurrentStep(2)} />;
      case 4:
        return <Step4Search reportId={reportId} splitIds={splitIds} onNext={handleStep4Next} onBack={() => setCurrentStep(3)} />;
      case 5:
        return <Step5Summary reportId={reportId} splitIds={splitIds} onNext={handleStep5Next} onBack={() => setCurrentStep(4)} />;
      case 6:
        return <Step6Final reportId={reportId} title={title} splitIds={splitIds} onBack={() => setCurrentStep(5)} />;
      default:
        return renderStartPage();
    }
  };

  return (
    <ConfigProvider locale={zhCN} theme={{ token: { colorPrimary: '#1890ff' } }}>
      <AntApp>
        <Layout style={{ minHeight: '100vh' }}>
          <Header style={{ background: '#fff', boxShadow: '0 2px 8px rgba(0,0,0,0.1)', display: 'flex', alignItems: 'center', padding: '0 24px' }}>
            <Title level={4} style={{ margin: 0, color: '#1890ff' }}>深度研究报告生成系统</Title>
            <div style={{ flex: 1 }} />
            {reportId && <Text type="secondary">报告ID: {reportId.substring(0, 8)}...</Text>}
          </Header>
          <Content style={{ padding: 0, background: '#f0f2f5' }}>
            {reportId && currentStep > 0 && currentStep <= 6 && (
              <div style={{ background: '#fff', marginBottom: 0 }}>
                <StepProgress currentStep={currentStep} onStepChange={handleStepChange} disabled />
              </div>
            )}
            <div style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
              {renderStepContent()}
            </div>
          </Content>
          <Footer style={{ textAlign: 'center', background: '#fff', marginTop: '24px' }}>
            深度研究报告生成系统 - FYP 2026
          </Footer>
        </Layout>
      </AntApp>
    </ConfigProvider>
  );
};

export default App;
