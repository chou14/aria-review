import { getOverview } from "./client";
import type { AnalysisPanelProps } from "../components/analysisViews";
import { asDbCorpusId, asRCorpusId } from "./corpusIds";

export function assertCorpusIdBrands(projectId: string): void {
  const dbCorpusId = asDbCorpusId(1);
  const rCorpusId = asRCorpusId("r-demo");

  void getOverview(projectId, rCorpusId);
  void ({ projectId, corpusId: rCorpusId } satisfies AnalysisPanelProps);

  // @ts-expect-error DB int corpusId 不能传给分析 REST。
  void getOverview(projectId, dbCorpusId);

  // @ts-expect-error 裸 number 不能传给分析 REST。
  void getOverview(projectId, 1);

  // @ts-expect-error 裸 string 必须先在统一出口品牌化。
  void ({ projectId, corpusId: "r-demo" } satisfies AnalysisPanelProps);
}
