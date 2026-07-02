import type { ReactNode } from "react";
import { OverviewPanel } from "./OverviewPanel";
import { SourcesPanel } from "./SourcesPanel";
import { AuthorsPanel } from "./AuthorsPanel";
import { DocumentsPanel } from "./DocumentsPanel";
import { ConceptualPanel } from "./ConceptualPanel";
import { IntellectualPanel } from "./IntellectualPanel";
import { SocialPanel } from "./SocialPanel";
import { ScreenPanel } from "./ScreenPanel";
import { PrismaPanel } from "./PrismaPanel";
import { ChatPanel } from "./ChatPanel";
import { AiToolsPanel } from "./AiToolsPanel";
import { ReviewPanel } from "./ReviewPanel";
import { ReportPanel } from "./ReportPanel";
import type { RCorpusId } from "../api/corpusIds";

export type AnalysisViewId =
  | "overview" | "sources" | "authors"
  | "documents" | "conceptual" | "intellectual" | "social"
  | "screen" | "prisma"
  | "chat" | "aitools" | "review" | "report";

export interface AnalysisPanelProps {
  projectId: string;
  corpusId: RCorpusId;
  llm?: { apiKey?: string; baseUrl?: string; model?: string };
}

export interface AnalysisViewDefinition {
  id: AnalysisViewId;
  label: string;
  icon: string;
  title: string;
  desc: string;
  requiresCorpus: boolean;
  requiresR: boolean;
  renderPanel: (props: AnalysisPanelProps) => ReactNode;
}

export interface AnalysisGroupDefinition {
  key: string;
  label: string;
  icon: string;
  views: AnalysisViewDefinition[];
}

export const DEFAULT_ANALYSIS_VIEW: AnalysisViewId = "overview";

export const ANALYSIS_GROUPS: AnalysisGroupDefinition[] = [
  {
    key: "stats",
    label: "统计概览",
    icon: "📊",
    views: [
      {
        id: "overview",
        label: "领域概览",
        icon: "🔭",
        title: "领域概览",
        desc: "年度产出、主要指标与总体态势",
        requiresCorpus: true,
        requiresR: true,
        renderPanel: (props) => <OverviewPanel projectId={props.projectId} corpusId={props.corpusId} />,
      },
      {
        id: "sources",
        label: "核心期刊",
        icon: "📰",
        title: "核心期刊",
        desc: "期刊来源分布、Bradford 核心区",
        requiresCorpus: true,
        requiresR: true,
        renderPanel: (props) => <SourcesPanel projectId={props.projectId} corpusId={props.corpusId} />,
      },
      {
        id: "authors",
        label: "核心作者",
        icon: "👤",
        title: "核心作者",
        desc: "作者产出量与影响力排名",
        requiresCorpus: true,
        requiresR: true,
        renderPanel: (props) => <AuthorsPanel projectId={props.projectId} corpusId={props.corpusId} />,
      },
    ],
  },
  {
    key: "knowledge",
    label: "知识结构",
    icon: "🕸",
    views: [
      {
        id: "documents",
        label: "关键词热点",
        icon: "🔑",
        title: "关键词热点",
        desc: "高频词与 TF-IDF 词云",
        requiresCorpus: true,
        requiresR: true,
        renderPanel: (props) => <DocumentsPanel projectId={props.projectId} corpusId={props.corpusId} />,
      },
      {
        id: "conceptual",
        label: "主题地图",
        icon: "🗺",
        title: "主题地图",
        desc: "共词聚类概念图谱（Thematic Map）",
        requiresCorpus: true,
        requiresR: true,
        renderPanel: (props) => <ConceptualPanel projectId={props.projectId} corpusId={props.corpusId} />,
      },
      {
        id: "intellectual",
        label: "知识脉络",
        icon: "📚",
        title: "知识脉络",
        desc: "引文耦合知识结构演化",
        requiresCorpus: true,
        requiresR: true,
        renderPanel: (props) => <IntellectualPanel projectId={props.projectId} corpusId={props.corpusId} />,
      },
      {
        id: "social",
        label: "合作网络",
        icon: "🤝",
        title: "合作网络",
        desc: "作者/机构/国家合作关系网络",
        requiresCorpus: true,
        requiresR: true,
        renderPanel: (props) => <SocialPanel projectId={props.projectId} corpusId={props.corpusId} />,
      },
    ],
  },
  {
    key: "library",
    label: "文献库洞察",
    icon: "🔍",
    views: [
      {
        id: "screen",
        label: "相关性筛选",
        icon: "🎯",
        title: "AI 相关性筛选",
        desc: "对文献进行 AI 相关性评分与排序",
        requiresCorpus: true,
        requiresR: true,
        renderPanel: (props) => <ScreenPanel projectId={props.projectId} corpusId={props.corpusId} />,
      },
      {
        id: "prisma",
        label: "PRISMA",
        icon: "📋",
        title: "PRISMA 流程图",
        desc: "生成系统综述 PRISMA 流程图",
        requiresCorpus: false,
        requiresR: false,
        renderPanel: (props) => <PrismaPanel projectId={props.projectId} />,
      },
    ],
  },
  {
    key: "aitools",
    label: "AI 工具台",
    icon: "🤖",
    views: [
      {
        id: "chat",
        label: "语料对话",
        icon: "💬",
        title: "语料对话",
        desc: "与当前语料进行多轮学术对话",
        requiresCorpus: true,
        requiresR: true,
        renderPanel: (props) => <ChatPanel projectId={props.projectId} corpusId={props.corpusId} llm={props.llm} />,
      },
      {
        id: "aitools",
        label: "AI 工具",
        icon: "⚙",
        title: "AI 工具",
        desc: "文本总结、翻译与改写",
        requiresCorpus: true,
        requiresR: true,
        renderPanel: (props) => <AiToolsPanel projectId={props.projectId} corpusId={props.corpusId} llm={props.llm} />,
      },
      {
        id: "review",
        label: "AI 综述",
        icon: "✍",
        title: "AI 文献综述",
        desc: "自动生成可引用的文献综述",
        requiresCorpus: false,
        requiresR: false,
        renderPanel: (props) => <ReviewPanel projectId={props.projectId} corpusId={props.corpusId} llm={props.llm} />,
      },
      {
        id: "report",
        label: "导出报告",
        icon: "📤",
        title: "导出报告与引用",
        desc: "下载 Markdown/HTML 报告及引用列表",
        requiresCorpus: true,
        requiresR: true,
        renderPanel: (props) => <ReportPanel projectId={props.projectId} corpusId={props.corpusId} />,
      },
    ],
  },
];

export const ANALYSIS_VIEWS = ANALYSIS_GROUPS.flatMap((group) => group.views);
export const ANALYSIS_VIEW_IDS = new Set<string>(ANALYSIS_VIEWS.map((view) => view.id));

export function isAnalysisViewId(value: string | undefined): value is AnalysisViewId {
  return Boolean(value && ANALYSIS_VIEW_IDS.has(value));
}

export function findAnalysisView(id: AnalysisViewId): AnalysisViewDefinition {
  const view = ANALYSIS_VIEWS.find((item) => item.id === id);
  if (!view) throw new Error(`Unknown analysis view: ${id}`);
  return view;
}

/** 兼容旧调用名：AnalysisFrame 标题栏只需要同一个 view definition。 */
export const findViewMeta = findAnalysisView;
