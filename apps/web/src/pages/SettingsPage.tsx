import { useEffect, useRef, useState } from "react";
import { pingImage, pingLlm, pingSciverse } from "../api/client";
import {
  PROVIDER_DEFAULT_BASE_URLS,
  PROVIDER_DEFAULT_MODELS,
  type LlmProvider,
  type LlmSettings,
  useLlmSettings,
} from "../api/useLlmSettings";
import {
  type SciverseSettings,
  useSciverseSettings,
} from "../api/useSciverseSettings";
import {
  type ImageSettings,
  useImageSettings,
} from "../api/useImageSettings";

const PROVIDER_LABELS: { value: LlmProvider; label: string; placeholder: string }[] = [
  { value: "deepseek", label: "DeepSeek", placeholder: "your_api_key_here" },
  { value: "openai", label: "OpenAI", placeholder: "your_api_key_here" },
  { value: "anthropic", label: "Anthropic", placeholder: "your_anthropic_api_key_here" },
];

type ConnectionErrorLike = {
  status?: number;
  code?: string;
  message?: string;
  friendlyMessage?: string;
};

function formatConnectionError(error: unknown, fallback: string): string {
  const err = error as ConnectionErrorLike;
  const status = err?.status;
  const code = err?.code ?? "";
  const message = err?.friendlyMessage || err?.message || "";

  if (status === 401 || status === 403) return "API Key 无效或无权限，请检查 Key 是否正确。";
  if (status === 404) return "Base URL 或模型名称错误，请检查接口地址和 Model 配置。";
  if (status === 429) return "请求频率或额度受限，请稍后重试或检查账户额度。";
  if (typeof status === "number" && status >= 500) return "上游服务暂时不可用，请稍后重试。";
  if (status === 0 || code === "NETWORK_ERROR" || /network|fetch|timeout|超时|无法连接/i.test(message)) {
    return "服务不可达，请确认后端/API 服务已启动，或检查网络连接。";
  }
  return message || fallback;
}

export function SettingsPage() {
  const { settings, save, clear } = useLlmSettings();
  const {
    settings: sciverseSettings,
    save: saveSciverse,
    clear: clearSciverse,
  } = useSciverseSettings();
  const {
    settings: imageSettings,
    save: saveImage,
    clear: clearImage,
  } = useImageSettings();

  const [form, setForm] = useState<LlmSettings>(settings);
  const [saved, setSaved] = useState(false);
  const [testState, setTestState] = useState<"idle" | "testing" | "ok" | "fail">("idle");
  const [testMsg, setTestMsg] = useState("");
  const llmTestSeqRef = useRef(0);

  const [sciverseForm, setSciverseForm] = useState<SciverseSettings>(sciverseSettings);
  const [sciverseSaved, setSciverseSaved] = useState(false);
  const [sciverseTestState, setSciverseTestState] = useState<"idle" | "testing" | "ok" | "fail">("idle");
  const [sciverseTestMsg, setSciverseTestMsg] = useState("");
  const sciverseTestSeqRef = useRef(0);

  const [imageForm, setImageForm] = useState<ImageSettings>(imageSettings);
  const [imageSaved, setImageSaved] = useState(false);
  const [imageTestState, setImageTestState] = useState<"idle" | "testing" | "ok" | "fail">("idle");
  const [imageTestMsg, setImageTestMsg] = useState("");
  const imageTestSeqRef = useRef(0);

  useEffect(() => {
    setForm(settings);
  }, [settings]);

  useEffect(() => {
    setSciverseForm(sciverseSettings);
  }, [sciverseSettings]);

  useEffect(() => {
    setImageForm(imageSettings);
  }, [imageSettings]);

  function handleProviderChange(p: LlmProvider) {
    setForm((f) => ({
      ...f,
      provider: p,
      baseUrl: PROVIDER_DEFAULT_BASE_URLS[p],
      model: PROVIDER_DEFAULT_MODELS[p],
    }));
  }

  function handleSave() {
    save(form);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  function handleClear() {
    llmTestSeqRef.current += 1;
    clear();
    setTestState("idle");
    setTestMsg("");
  }

  async function handleTest() {
    const seq = ++llmTestSeqRef.current;
    if (!form.apiKey.trim()) {
      setTestState("fail");
      setTestMsg("请先填写 API Key");
      return;
    }
    setTestState("testing");
    setTestMsg("");
    try {
      const res = await pingLlm({
        apiKey: form.apiKey.trim(),
        baseUrl: form.baseUrl.trim() || undefined,
        model: form.model.trim() || undefined,
      });
      if (seq !== llmTestSeqRef.current) return;
      setTestState("ok");
      setTestMsg(`LLM 可用，model=${res.model}，返回 ${res.content || "(空)"}`);
    } catch (e) {
      if (seq !== llmTestSeqRef.current) return;
      setTestState("fail");
      setTestMsg(formatConnectionError(e, "LLM 测试失败，请检查 Base URL / Key / Model"));
    }
  }

  function handleSciverseSave() {
    saveSciverse(sciverseForm);
    setSciverseSaved(true);
    setTimeout(() => setSciverseSaved(false), 2000);
  }

  function handleSciverseClear() {
    sciverseTestSeqRef.current += 1;
    clearSciverse();
    setSciverseTestState("idle");
    setSciverseTestMsg("");
  }

  async function handleSciverseTest() {
    const seq = ++sciverseTestSeqRef.current;
    if (!sciverseForm.apiToken.trim()) {
      setSciverseTestState("fail");
      setSciverseTestMsg("请先填写 Sciverse API Token");
      return;
    }
    setSciverseTestState("testing");
    setSciverseTestMsg("");
    try {
      const res = await pingSciverse({
        apiToken: sciverseForm.apiToken.trim(),
        baseUrl: sciverseForm.baseUrl.trim() || undefined,
      });
      if (seq !== sciverseTestSeqRef.current) return;
      setSciverseTestState("ok");
      setSciverseTestMsg(`Sciverse 可用，baseUrl=${res.baseUrl}，测试返回 ${res.resultCount} 条`);
    } catch (e) {
      if (seq !== sciverseTestSeqRef.current) return;
      setSciverseTestState("fail");
      setSciverseTestMsg(formatConnectionError(e, "Sciverse 测试失败，请检查 Base URL / Token"));
    }
  }

  function handleImageSave() {
    saveImage(imageForm);
    setImageSaved(true);
    setTimeout(() => setImageSaved(false), 2000);
  }

  function handleImageClear() {
    imageTestSeqRef.current += 1;
    clearImage();
    setImageTestState("idle");
    setImageTestMsg("");
  }

  async function handleImageTest() {
    const seq = ++imageTestSeqRef.current;
    if (!imageForm.apiKey.trim()) {
      setImageTestState("fail");
      setImageTestMsg("请先填写生图 API Key");
      return;
    }
    setImageTestState("testing");
    setImageTestMsg("");
    try {
      const res = await pingImage({
        apiKey: imageForm.apiKey.trim(),
        baseUrl: imageForm.baseUrl.trim() || undefined,
        model: imageForm.model.trim() || undefined,
        size: imageForm.size.trim() || undefined,
      });
      if (seq !== imageTestSeqRef.current) return;
      setImageTestState("ok");
      setImageTestMsg(`生图模型可用：model=${res.model}，size=${res.size}`);
    } catch (e) {
      if (seq !== imageTestSeqRef.current) return;
      setImageTestState("fail");
      setImageTestMsg(formatConnectionError(e, "生图模型测试失败，请检查 Base URL / Key / Model"));
    }
  }

  return (
    <div className="container" style={{ padding: "2rem 1.5rem", maxWidth: 640 }}>
      <h2>设置</h2>

      <div className="card" style={{ marginTop: "1rem" }}>
        <h3 style={{ marginTop: 0 }}>LLM 配置</h3>
        <p
          className="muted"
          style={{
            fontSize: "0.82rem",
            background: "var(--warn-soft, #fef3c7)",
            borderLeft: "3px solid var(--warn, #b8791a)",
            padding: "0.5rem 0.75rem",
            marginBottom: "1.25rem",
            borderRadius: "0 4px 4px 0",
          }}
        >
          API Key 仅存储于本地浏览器 localStorage，<strong>不上传服务端数据库</strong>。
          每次 LLM 请求时通过 <code>X-LLM-*</code> 请求头发送给后端。
        </p>

        <div style={{ marginBottom: "1rem" }}>
          <label htmlFor="llm-provider" style={{ display: "block", fontWeight: 600, marginBottom: "0.35rem", fontSize: "0.9rem" }}>
            Provider
          </label>
          <select
            id="llm-provider"
            value={form.provider}
            onChange={(e) => handleProviderChange(e.target.value as LlmProvider)}
            style={{ width: "100%" }}
          >
            {PROVIDER_LABELS.map(({ value, label }) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </div>

        <div style={{ marginBottom: "1rem" }}>
          <label htmlFor="llm-apikey" style={{ display: "block", fontWeight: 600, marginBottom: "0.35rem", fontSize: "0.9rem" }}>
            API Key
          </label>
          <input
            id="llm-apikey"
            type="password"
            value={form.apiKey}
            placeholder={PROVIDER_LABELS.find((p) => p.value === form.provider)?.placeholder ?? "your_api_key_here"}
            onChange={(e) => setForm((f) => ({ ...f, apiKey: e.target.value }))}
            autoComplete="off"
            style={{ width: "100%", boxSizing: "border-box" }}
          />
        </div>

        <div style={{ marginBottom: "1rem" }}>
          <label htmlFor="llm-baseurl" style={{ display: "block", fontWeight: 600, marginBottom: "0.35rem", fontSize: "0.9rem" }}>
            Base URL
          </label>
          <input
            id="llm-baseurl"
            type="url"
            value={form.baseUrl}
            placeholder="https://api.openai.com/v1"
            onChange={(e) => setForm((f) => ({ ...f, baseUrl: e.target.value }))}
            autoComplete="off"
            style={{ width: "100%", boxSizing: "border-box" }}
          />
          <p className="muted" style={{ fontSize: "0.78rem", marginTop: "0.25rem" }}>
            OpenAI 兼容接口地址，后端会请求 <code>/chat/completions</code>；内网地址默认会被拒绝，确需使用时在 Agent 环境中开启 <code>BIBLIOCN_ALLOW_PRIVATE_API_BASE_URLS</code>。
          </p>
        </div>

        <div style={{ marginBottom: "1.25rem" }}>
          <label htmlFor="llm-model" style={{ display: "block", fontWeight: 600, marginBottom: "0.35rem", fontSize: "0.9rem" }}>
            模型
          </label>
          <input
            id="llm-model"
            type="text"
            value={form.model}
            onChange={(e) => setForm((f) => ({ ...f, model: e.target.value }))}
            style={{ width: "100%", boxSizing: "border-box" }}
          />
        </div>

        <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
          <button type="button" className="btn" onClick={handleSave}>
            {saved ? "已保存" : "保存"}
          </button>
          <button type="button" className="btn btn-ghost" onClick={handleClear}>
            清除
          </button>
          <button type="button" className="btn btn-ghost" onClick={() => void handleTest()}>
            {testState === "testing" ? "测试中..." : "测试连接"}
          </button>
        </div>

        {testState !== "idle" && testMsg && (
          <p role="status" style={{ marginTop: "0.75rem", fontSize: "0.84rem", color: testState === "ok" ? "var(--green, #16a34a)" : testState === "fail" ? "crimson" : "var(--ink-2)" }}>
            {testMsg}
          </p>
        )}
      </div>

      <div className="card" style={{ marginTop: "1.25rem" }}>
        <h3 style={{ marginTop: 0 }}>Sciverse API 配置</h3>
        <p className="muted" style={{ fontSize: "0.82rem", marginBottom: "1rem" }}>
          Token 仅存储于本地浏览器，调用时通过 <code>X-Sciverse-*</code> 请求头发送给后端；
          服务端也支持 <code>SCIVERSE_BASE_URL</code> 和 <code>SCIVERSE_API_TOKEN</code> 环境变量。
        </p>

        <div style={{ marginBottom: "1rem" }}>
          <label htmlFor="sciverse-baseurl" style={{ display: "block", fontWeight: 600, marginBottom: "0.35rem", fontSize: "0.9rem" }}>
            Base URL
          </label>
          <input
            id="sciverse-baseurl"
            type="url"
            value={sciverseForm.baseUrl}
            placeholder="https://api.sciverse.space"
            onChange={(e) => setSciverseForm((f) => ({ ...f, baseUrl: e.target.value }))}
            autoComplete="off"
            style={{ width: "100%", boxSizing: "border-box" }}
          />
        </div>

        <div style={{ marginBottom: "1.25rem" }}>
          <label htmlFor="sciverse-token" style={{ display: "block", fontWeight: 600, marginBottom: "0.35rem", fontSize: "0.9rem" }}>
            API Token
          </label>
          <input
            id="sciverse-token"
            type="password"
            value={sciverseForm.apiToken}
            placeholder="Bearer token"
            onChange={(e) => setSciverseForm((f) => ({ ...f, apiToken: e.target.value }))}
            autoComplete="off"
            style={{ width: "100%", boxSizing: "border-box" }}
          />
        </div>

        <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
          <button type="button" className="btn" onClick={handleSciverseSave}>
            {sciverseSaved ? "已保存" : "保存 Sciverse"}
          </button>
          <button type="button" className="btn btn-ghost" onClick={handleSciverseClear}>
            清除
          </button>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => void handleSciverseTest()}
          >
            {sciverseTestState === "testing" ? "测试中..." : "测试连接"}
          </button>
        </div>

        {sciverseTestState !== "idle" && sciverseTestMsg && (
          <p role="status" style={{ marginTop: "0.75rem", fontSize: "0.84rem", color: sciverseTestState === "ok" ? "var(--green, #16a34a)" : sciverseTestState === "fail" ? "crimson" : "var(--ink-2)" }}>
            {sciverseTestMsg}
          </p>
        )}
      </div>

      <div className="card" style={{ marginTop: "1.25rem" }}>
        <h3 style={{ marginTop: 0 }}>生图模型配置</h3>
        <p className="muted" style={{ fontSize: "0.82rem", marginBottom: "1rem" }}>
          用于 AI 工具台「一图读懂」的第二步生图。Key 仅保存在浏览器本地，调用时通过 <code>X-Image-*</code> 请求头透传。
        </p>

        <div style={{ marginBottom: "1rem" }}>
          <label htmlFor="image-baseurl" style={{ display: "block", fontWeight: 600, marginBottom: "0.35rem", fontSize: "0.9rem" }}>
            生图 Base URL
          </label>
          <input
            id="image-baseurl"
            type="url"
            value={imageForm.baseUrl}
            placeholder="https://api.openai.com/v1"
            onChange={(e) => setImageForm((f) => ({ ...f, baseUrl: e.target.value }))}
            autoComplete="off"
            style={{ width: "100%", boxSizing: "border-box" }}
          />
        </div>

        <div style={{ marginBottom: "1rem" }}>
          <label htmlFor="image-apikey" style={{ display: "block", fontWeight: 600, marginBottom: "0.35rem", fontSize: "0.9rem" }}>
            生图 API Key
          </label>
          <input
            id="image-apikey"
            type="password"
            value={imageForm.apiKey}
            placeholder="your_api_key_here"
            onChange={(e) => setImageForm((f) => ({ ...f, apiKey: e.target.value }))}
            autoComplete="off"
            style={{ width: "100%", boxSizing: "border-box" }}
          />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 160px", gap: "0.75rem", marginBottom: "1.25rem" }}>
          <label htmlFor="image-model" style={{ display: "block", fontWeight: 600, fontSize: "0.9rem" }}>
            生图模型
            <input
              id="image-model"
              type="text"
              value={imageForm.model}
              placeholder="gpt-image-1"
              onChange={(e) => setImageForm((f) => ({ ...f, model: e.target.value }))}
              style={{ width: "100%", boxSizing: "border-box", marginTop: "0.35rem" }}
            />
          </label>
          <label htmlFor="image-size" style={{ display: "block", fontWeight: 600, fontSize: "0.9rem" }}>
            尺寸
            <input
              id="image-size"
              type="text"
              value={imageForm.size}
              placeholder="1024x1024"
              onChange={(e) => setImageForm((f) => ({ ...f, size: e.target.value }))}
              style={{ width: "100%", boxSizing: "border-box", marginTop: "0.35rem" }}
            />
          </label>
        </div>

        <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
          <button type="button" className="btn" onClick={handleImageSave}>
            {imageSaved ? "已保存" : "保存生图配置"}
          </button>
          <button type="button" className="btn btn-ghost" onClick={handleImageClear}>
            清除
          </button>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => void handleImageTest()}
          >
            {imageTestState === "testing" ? "测试中..." : "测试生图连接"}
          </button>
        </div>

        {imageTestState !== "idle" && imageTestMsg && (
          <p role="status" style={{ marginTop: "0.75rem", fontSize: "0.84rem", color: imageTestState === "ok" ? "var(--green, #16a34a)" : imageTestState === "fail" ? "crimson" : "var(--ink-2)" }}>
            {imageTestMsg}
          </p>
        )}
      </div>

      <div className="card" style={{ marginTop: "1.25rem", opacity: 0.6 }}>
        <h3 style={{ marginTop: 0, fontSize: "0.95rem" }}>
          费用 / Token 看板
          <span className="milestone-tag" style={{ marginLeft: "0.5rem", fontSize: "0.72rem" }}>即将支持</span>
        </h3>
        <p className="muted" style={{ fontSize: "0.83rem" }}>
          Token 消耗统计与费用估算将在后续迭代接入。
        </p>
      </div>
    </div>
  );
}
