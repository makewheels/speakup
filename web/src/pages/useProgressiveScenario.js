import { useRef, useState } from "react";

import { api } from "../api/client.js";

// 渐进式场景提示 + 指定题目（?scenario=<slug>）待选题状态。
// 规格：docs/requirements/20260826-渐进式场景提示.md；计数与幂等以服务端为准。
export default function useProgressiveScenario(t) {
  const [pendingScenario, setPendingScenario] = useState(null);
  const [hintCount, setHintCount] = useState(0);
  const [hintBusy, setHintBusy] = useState(false);
  const [hintError, setHintError] = useState("");
  const startRequestIdRef = useRef("");

  const reset = () => {
    setPendingScenario(null);
    setHintCount(0);
    setHintBusy(false);
    setHintError("");
    startRequestIdRef.current = "";
  };

  // 指定题目入口：精确取题；失败给 unavailable 态，绝不回退随机题
  const loadBySlug = async (slug, onPhase) => {
    onPhase("loading");
    try {
      const scenario = await api.scenarioBySlug(slug);
      setPendingScenario(scenario);
      onPhase("ready");
    } catch {
      setPendingScenario(null);
      onPhase("scenarioUnavailable");
    }
  };

  // 开始动作才创建真实 Session；重试复用同一 requestId，服务端幂等去重，
  // 一个开始动作只产生一个 Session；创建成功后由调用方 replace 到规范 Session URL
  const createPendingSession = async (userId) => {
    if (!startRequestIdRef.current) startRequestIdRef.current = crypto.randomUUID();
    const session = await api.createPractice({
      userId,
      scenarioId: pendingScenario.scenarioId,
      requestId: startRequestIdRef.current,
    });
    setHintCount(session.revealedHintCount ?? 0);
    return session;
  };

  const restoreHintCount = (session) => setHintCount(session?.revealedHintCount ?? 0);

  // 提示按服务端计数逐条领取；失败不提前显示提示，只给可重试错误
  const revealNextHint = async (practiceId) => {
    if (!practiceId || hintBusy) return;
    setHintBusy(true);
    setHintError("");
    try {
      const res = await api.revealNextHint(practiceId, crypto.randomUUID());
      setHintCount(res.revealedHintCount);
    } catch (err) {
      setHintError(t("practice.hintFailed", { msg: err.message }));
    } finally {
      setHintBusy(false);
    }
  };

  return {
    pendingScenario, hintCount, hintBusy, hintError,
    reset, loadBySlug, createPendingSession, restoreHintCount, revealNextHint,
  };
}
