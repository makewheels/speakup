// 评估 SSE 流：把已提交文本送去流式评估，并把结果写回页面状态。
// 页面只传状态 setter 与会话上下文（PracticePage.evaluate 的薄封装）。
import { api, correctStream } from "../api/client.js";

import { EMPTY_FEEDBACK, hasUsableFeedback, reviewMapFromGaps } from "./practiceFeedbackState.js";
import { trackPracticeResult } from "./practiceTelemetry.js";

export function startEvaluation(ctx) {
  const {
    text, active, userId, hintCount, round, t, navigate,
    evalTimerRef, sseControllerRef, takeAudioBlob, resetChat,
    setResult, setFeedbackLoading, setPhase, setEvalElapsed, setStreamingLen,
    setActiveAttemptId, setRound, setSavedMap, setFeedbackActionsDisabled,
  } = ctx;

  setResult(EMPTY_FEEDBACK);
  setFeedbackLoading(true);
  setPhase("feedback");
  setEvalElapsed(0);
  setStreamingLen(0);
  evalTimerRef.current = setInterval(() => setEvalElapsed((sec) => sec + 1), 1000);

  sseControllerRef.current = correctStream(
    {
      userId,
      practiceId: active._id,
      text,
      // 自由说：不判任务完成度，后端据此走 FREE prompt；话题一并落 attempt
      mode: active.mode === "free" ? "free" : "scenario",
      freeTopic: active.freeTopic || "",
    },
    {
      onStarted: ({ attemptId, round: startedRound }) => {
        setActiveAttemptId(attemptId);
        if (startedRound) setRound(startedRound);
        navigate(`/practice/${active._id}?attempt=${attemptId}`, { replace: true });
      },
      onChunk: (chunk) => setStreamingLen((n) => n + chunk.length),
      onDone: ({ result: res, attemptId, round: r }) => {
        clearInterval(evalTimerRef.current);
        if (!hasUsableFeedback(res)) {
          alert(t("practice.feedbackFailed", { msg: res?.summary || t("practice.emptyFeedback") }));
          setFeedbackLoading(false);
          setResult(null);
          setPhase("review");
          navigate(`/practice/${active._id}`, { replace: true });
          return;
        }
        setResult(res);
        setFeedbackLoading(false);
        trackPracticeResult({ active, result: res, round: r ?? round, userId, attemptId, hintCount });
        // AI 自动收录的 gap 回传了 reviewItemId，用它初始化收录态（这样「已在错题本」可直接取消）
        setSavedMap(reviewMapFromGaps(res.gaps));
        if (r) {
          setRound(r);
        }
        if (attemptId) {
          setActiveAttemptId(attemptId);
          navigate(`/practice/${active._id}?attempt=${attemptId}`, { replace: true });
        }
        resetChat();
        // 结果页首帧在绘制前回到顶部；后续流式完成和媒体加载不再重复滚动。
        setFeedbackActionsDisabled(true);
        setTimeout(() => setFeedbackActionsDisabled(false), 1500);
        // URL 标记具体轮次，刷新能恢复到同一个 attempt。
        // 必须用 navigate 显式带 pathname：setSearchParams 在当前 react-router 版本下会丢掉
        // pathname 使 useParams 的 practiceId 变空，触发 useEffect 走"无 practiceId"分支自动跳下一题。
        // 评估完成后异步上传完整原声，供历史回听；当前不再触发发音评测。
        const audioBlob = takeAudioBlob();
        if (audioBlob && active?._id && attemptId) {
          api.uploadRecording(active._id, userId, audioBlob, attemptId)
            .catch((error) => console.warn("Recording upload unavailable:", error));
        }
      },
      onError: (err) => {
        clearInterval(evalTimerRef.current);
        alert(t("practice.feedbackFailed", { msg: err.message }));
        setFeedbackLoading(false);
        setResult(null);
        setActiveAttemptId("");
        setPhase("review");
        navigate(`/practice/${active._id}`, { replace: true });
      },
    }
  );
}
