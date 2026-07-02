/**
 * corpus id 品牌类型。
 *
 * DB corpusId 是 Postgres integer；R corpusId 是分析服务字符串。
 * 二者运行时仍是 number/string，仅在编译期阻止误传。
 */
export type DbCorpusId = number & { readonly __brand: "DbCorpusId" };
export type RCorpusId = string & { readonly __brand: "RCorpusId" };

export function asDbCorpusId(value: number): DbCorpusId {
  return value as DbCorpusId;
}

export function asRCorpusId(value: string): RCorpusId {
  return value as RCorpusId;
}

export type BrandCorpusIdFields<T extends { corpusId: number; rCorpusId?: string | null }> =
  Omit<T, "corpusId" | "rCorpusId"> & {
    corpusId: DbCorpusId;
    rCorpusId?: RCorpusId | null;
  };
