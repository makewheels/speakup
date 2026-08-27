import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { useUser } from "../context/useUser.js";
import { useT } from "../i18n/useI18n.js";
import { api } from "../api/client.js";
import PracticeActiveView from "../components/practice/PracticeActiveView.jsx";
import PracticeFeedbackView from "../components/practice/PracticeFeedbackView.jsx";
import PracticeModeSwitch from "../components/practice/PracticeModeSwitch.jsx";
import PracticePrefsWelcome from "../components/practice/PracticePrefsWelcome.jsx";
import PracticeUnavailable from "../components/practice/PracticeUnavailable.jsx";
import {
  getPracticePreferences,
  hasPracticePreferences,
  savePracticePreferences,
} from "../lib/practicePreferences.js";
import { useReviewCollection } from "./useReviewCollection.js";
import useFreeTopic from "./useFreeTopic.js";
import useFollowupChat from "./useFollowupChat.js";
import usePressGuard from "./usePressGuard.js";
import usePracticeRecorder from "./usePracticeRecorder.js";
import useProgressiveScenario from "./useProgressiveScenario.js";
import { resolveRequestedAttempt } from "./practiceAttemptRouting.js";
import { readSkippedScenarios, writeSkippedScenarios } from "./practiceSkippedScenarios.js";
import { startEvaluation } from "./practiceEvaluation.js";
import { trackPracticeRecordingStarted } from "./practiceTelemetry.js";
import { resultFromAttempt, reviewMapFromGaps } from "./practiceFeedbackState.js";
import useResultShare from "./useResultShare.js";

export default function PracticePage() {
  const { practiceId } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { user } = useUser();
  const t = useT();

  // 练习模式：scenario 场景题 / free 自由说。初值从 URL 还原（?mode=free），切换时写回 URL
  const [mode, setMode] = useState(() => (searchParams.get("mode") === "free" ? "free" : "scenario"));
  // 自由说话题（抽题/去重在 useFreeTopic 里）
  const { freeTopic, loadTopic, clearTopic, hasTopic } = useFreeTopic(user.userId);
  const { pressStart, pressEnd, pressClick, pressCancel } = usePressGuard();

  const [session, setSession] = useState(null);
  const [phase, setPhase] = useState("loading");
  // 渐进式提示与指定题目待选题：计数/幂等以服务端为准（useProgressiveScenario）
  const progressive = useProgressiveScenario(t);
  const { pendingScenario, hintCount, hintBusy, hintError } = progressive;
  const [practicePrefs, setPracticePrefs] = useState(() => getPracticePreferences(user.userId));
  const [needsPrefs, setNeedsPrefs] = useState(
    () => !practiceId && mode !== "free" && !searchParams.get("scenario")
      && !hasPracticePreferences(user.userId),
  );
  const [transcript, setTranscript] = useState("");
  const [transcriptionError, setTranscriptionError] = useState(false);
  const [result, setResult] = useState(null);
  const [feedbackLoading, setFeedbackLoading] = useState(false);
  const [activeAttemptId, setActiveAttemptId] = useState("");
  // 错题本收录：gap 作为错题收录；好表达笔记从结果文字中手动选中添加
  const {
    savedMap, setSavedMap, resetReviewCollection, toggleGap,
  } = useReviewCollection(session, activeAttemptId);
  const [round, setRound] = useState(1);
  const {
    closeShareLink, copyShareLink, resetShare, shareBusy, shareLink, shareResult, shareStatus,
  } = useResultShare({
    session, setSession, t, userId: user.userId,
  });
  const [hintGaps, setHintGaps] = useState([]);
  const [hintAttemptId, setHintAttemptId] = useState("");
  const [evalElapsed, setEvalElapsed] = useState(0);
  const [streamingLen, setStreamingLen] = useState(0);
  const [feedbackActionsDisabled, setFeedbackActionsDisabled] = useState(false);
  // 追问教练对话（流式）：question 从输入框取，错误文案用 i18n 在调用处拼
  const { chat, chatInput, setChatInput, chatBusy, sendChat: sendChatStream, resetChat } =
    useFollowupChat(user.userId, session?._id, activeAttemptId);
  const {
    elapsed, paused, pauseSupported,
    resetCapture, startCapture, stopCapture, pauseResumeCapture,
    discardCapture, takeAudioBlob,
  } = usePracticeRecorder();
  const evalTimerRef = useRef(null);
  const evalAnchorRef = useRef(null);
  const sseControllerRef = useRef(null);

  // 一轮新练习的公共状态重置（场景题 / 自由说共用）
  const resetRoundState = () => {
    setPhase("loading");
    setResult(null);
    setFeedbackLoading(false);
    setTranscript("");
    setTranscriptionError(false);
    resetShare();
    setRound(1);
    setActiveAttemptId("");
    setHintGaps([]);
    setHintAttemptId("");
    resetReviewCollection();
    resetCapture();
    setSession(null);
    progressive.reset();
  };

  const startNewRound = async (extraSkip = null, overridePrefs = null) => {
    resetRoundState();
    clearTopic();
    let skipped = readSkippedScenarios(user.userId);
    if (extraSkip && !skipped.includes(extraSkip)) {
      skipped = [...skipped, extraSkip];
      writeSkippedScenarios(user.userId, skipped);
    }
    try {
      const activePrefs = overridePrefs || getPracticePreferences(user.userId);
      setPracticePrefs(activePrefs);
      const scenario = await api.nextScenario(user.userId, skipped, activePrefs);
      const sess = await api.createPractice({
        userId: user.userId,
        scenarioId: scenario.scenarioId,
        requestId: crypto.randomUUID(),
      });
      setSession({
        ...sess,
        isCustom: scenario.isCustom,
        preferenceMatch: scenario.preferenceMatch,
      });
      // URL 带上 practiceId，方便分享 / 复制 id 排查（不重新触发加载）
      navigate(`/practice/${sess._id}`, { replace: true });
      setPhase("ready");
    } catch (err) {
      alert(t("practice.loadScenarioFailed", { msg: err.message }));
      setPhase("ready");
    }
  };

  // 自由说新一轮：抽一个没说过的话题（后端池子用完自动补题）。
  // 不在这里 navigate——调用方负责 URL；effect 回流的重复抽题由 useFreeTopic 去重。
  const startNewFreeRound = async () => {
    resetRoundState();
    clearTopic();
    try {
      await loadTopic();
      setPhase("ready");
    } catch (err) {
      // 抽不到话题不阻塞开口：提示后停在 ready，用户仍可「不用题目，随便说」
      alert(t("practice.loadTopicFailed", { msg: err.message }));
      setPhase("ready");
    }
  };

  // 「换一个话题」/ 自由说结果页的「下一个话题」
  const handleNextFreeRound = () => {
    startNewFreeRound();
    if (practiceId) navigate("/practice?mode=free");
  };

  // 模式切换：scenario ↔ free。URL 跟着变（可刷新还原），加载由 effect / 直接调用驱动
  const switchMode = (m) => {
    if (m === mode) return;
    setMode(m);
    if (m === "free") {
      setNeedsPrefs(false);
      if (!practiceId) startNewFreeRound();   // URL 不变（/practice），effect 不会回流，直接抽
      else navigate("/practice?mode=free");
      return;
    }
    // 切回场景题
    if (!practiceId) {
      if (hasPracticePreferences(user.userId)) startNewRound();
      else setNeedsPrefs(true);
      return;
    }
    navigate("/practice");
  };

  useEffect(() => {
    // 已经在内存里加载好这道题（刚 startNewRound 后 navigate 改 URL 触发的回流）就别再拉
    if (practiceId && session?._id === practiceId) return;
    if (practiceId) {
      api.getPractice(practiceId).then((s) => {
        setSession(s);
        progressive.restoreHintCount(s);
        // 会话模式决定顶部切换器高亮与「下一个」行为（旧数据无 mode 按场景题）
        setMode(s?.mode === "free" ? "free" : "scenario");
        const attempts = s.attempts ?? [];
        const requested = resolveRequestedAttempt(attempts, searchParams);
        if (requested) {
          const selectedAttempt = requested.attempt;
          setResult(resultFromAttempt(selectedAttempt));
          setTranscript(selectedAttempt.transcript ?? "");
          setSavedMap(reviewMapFromGaps(selectedAttempt.gaps));
          setRound(requested.round);
          setActiveAttemptId(requested.attemptId);
          resetChat(selectedAttempt.chat);
          setPhase("feedback");
          if (requested.shouldReplace) {
            navigate(`/practice/${practiceId}?attempt=${requested.attemptId}`, { replace: true });
          }
        } else {
          setActiveAttemptId("");
          setRound(attempts.length + 1);
          setPhase("ready");
        }
      }).catch(console.error);
      return;
    }
    const slug = searchParams.get("scenario");
    if (slug) {
      progressive.loadBySlug(slug, setPhase);
      return;
    }
    if (mode === "free") {
      // 自由说：抽一个没说过的话题。回流去重：已有话题/正在抽就不重复请求。
      // 微任务延迟同场景题分支：不在 effect 里同步 setState
      if (!hasTopic()) Promise.resolve().then(startNewFreeRound);
      return;
    }
    if (!hasPracticePreferences(user.userId)) {
      return;
    }
    const prefs = getPracticePreferences(user.userId);
    let cancelled = false;
    Promise.resolve().then(() => {
      if (!cancelled) startNewRound(null, prefs);
    });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [practiceId]);

  // 组件卸载时取消 SSE（录音机由 usePracticeRecorder 自行清理）
  useEffect(() => () => {
    sseControllerRef.current?.abort();
    pressCancel();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 评估开始时自动滚到进度处：流式 token 回显在按钮下方，移动端常在视口外
  useEffect(() => {
    if (phase === "evaluating") {
      evalAnchorRef.current?.scrollIntoView?.({ behavior: "smooth", block: "center" });
    }
  }, [phase]);

  const startWithPreferences = () => {
    const saved = savePracticePreferences(user.userId, practicePrefs);
    setPracticePrefs(saved);
    setNeedsPrefs(false);
    startNewRound(null, saved);
  };

  // 同一场景再说一遍：保留 session，带着上一轮差距提示重录（不封顶，可无限重说）
  const retrySame = () => {
    setHintGaps((result?.gaps ?? []).filter((g) => g.better));
    setHintAttemptId(activeAttemptId);
    setResult(null);
    setFeedbackLoading(false);
    setTranscript("");
    setTranscriptionError(false);
    resetShare();
    setRound((r) => r + 1);
    setActiveAttemptId("");
    resetReviewCollection();
    setPhase("ready");
    // 离开结果态，清掉 attempt 标记；显式带 pathname，避免只改查询参数时触发自动跳题。
    if (session?._id) navigate(`/practice/${session._id}`, { replace: true });
    window.scrollTo(0, 0);
  };

  // sessOverride：自由说的会话是本次录音刚建的，onstop 闭包里 session state 还是旧值，显式传入
  function evaluate(textOverride = null, sessOverride = null) {
    const active = sessOverride || session;
    const text = (textOverride ?? transcript).trim();
    if (!text || !active) return;
    startEvaluation({
      text, active, userId: user.userId, hintCount, round, t, navigate,
      evalTimerRef, sseControllerRef, takeAudioBlob, resetChat,
      setResult, setFeedbackLoading, setPhase, setEvalElapsed, setStreamingLen,
      setActiveAttemptId, setRound, setSavedMap, setFeedbackActionsDisabled,
    });
  }

  // 录完一段的后续流转：转写 → 有文本就评估，否则回到可手动输入态
  // sess 而非 session state：自由说的会话是本次录音刚建的，闭包里 state 还是旧值
  const transcribeAndEvaluate = async (blob, sess) => {
    setPhase("transcribing");
    try {
      const { text: txt } = await api.transcribeAudio(user.userId, blob, sess?._id);
      setTranscript(txt || "");
      setTranscriptionError(false);
      if ((txt || "").trim()) {
        evaluate(txt, sess);
      } else {
        setPhase("review");
      }
    } catch (err) {
      console.warn("Cloud transcription unavailable:", err);
      setTranscriptionError(true);
      setPhase("review");
    }
  };

  // opts.forceNoTopic：「不用题目，随便说」入口——state 更新异步，这里直接按无话题建会话
  const startRecording = useCallback(async (opts = {}) => {
    if (location.protocol === "http:" && location.hostname !== "localhost") {
      alert(t("practice.needHttps"));
      return;
    }

    const topic = opts.forceNoTopic ? null : freeTopic;
    // 自由说的会话延迟到点录音才建（没开口不留空记录）；场景题会话在抽题时已建好
    let sess = session;
    if (mode === "free" && !sess) {
      try {
        sess = await api.createPractice({
          userId: user.userId,
          mode: "free",
          freeTopicId: topic?._id || "",
          freeTopic: topic?.text || "",
        });
        setSession(sess);
        navigate(`/practice/${sess._id}?mode=free`, { replace: true });
      } catch (err) {
        alert(t("practice.loadScenarioFailed", { msg: err.message }));
        return;
      }
    }
    if (mode === "scenario" && !sess && pendingScenario) {
      // 指定题目：开始动作才建真实 Session；同 requestId 服务端幂等去重
      try {
        sess = await progressive.createPendingSession(user.userId);
      } catch (err) {
        alert(t("practice.loadScenarioFailed", { msg: err.message }));
        return;
      }
      setSession(sess);
      navigate(`/practice/${sess._id}`, { replace: true });
    }

    setTranscript("");
    setTranscriptionError(false);
    setResult(null);
    setPhase("recording");

    const started = await startCapture({
      onComplete: (blob) => transcribeAndEvaluate(blob, sess),
      onMicError: (err) => {
        alert(t("practice.micFailed", { msg: err.message }));
        setPhase("ready");
      },
    });
    if (started) trackPracticeRecordingStarted(sess || session, user.userId, hintCount);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, t, session, mode, freeTopic, startCapture, pendingScenario, hintCount]);

  // 重录：丢弃本次录音回到 ready，不转写不评估（onstop 里由钩子的 discardRef 短路）
  const discardRecording = () => {
    if (!discardCapture()) return;
    setTranscript("");
    setPhase("ready");
    window.scrollTo(0, 0);
  };

  // 追问：基于本次反馈继续问 AI（流式逻辑在 useFollowupChat），这里只补 i18n 错误文案
  const sendChat = () => sendChatStream(chatInput, (err) => t("practice.chatError", { msg: err.message }));

  // 「不用题目，随便说」：清空话题立即开录（会话按无话题创建）
  const startNoTopic = () => {
    clearTopic();
    startRecording({ forceNoTopic: true });
  };

  // 结果页「下一个」：自由说换新话题，场景题换新场景
  const handleFeedbackNext = (skipId) => {
    if (session?.mode === "free") handleNextFreeRound();
    else startNewRound(skipId);
  };

  const scenario = session?.scenario ?? pendingScenario;
  const modeSwitch = <PracticeModeSwitch mode={mode} onSwitch={switchMode} t={t} />;

  if (needsPrefs) {
    return (
      <PracticePrefsWelcome
        modeSwitch={modeSwitch}
        value={practicePrefs}
        onChange={setPracticePrefs}
        onStart={startWithPreferences}
        t={t}
      />
    );
  }

  if (phase === "scenarioUnavailable") {
    return <PracticeUnavailable modeSwitch={modeSwitch} onBack={() => navigate("/practice")} t={t} />;
  }

  if (phase === "feedback" && result) {
    return (
      <PracticeFeedbackView
        attemptId={activeAttemptId}
        chat={chat}
        chatBusy={chatBusy}
        chatInput={chatInput}
        result={result}
        loading={feedbackLoading}
        streamingLen={streamingLen}
        retrySame={retrySame}
        round={round}
        savedMap={savedMap}
        scenario={scenario}
        sendChat={sendChat}
        session={session}
        setChatInput={setChatInput}
        startNewRound={handleFeedbackNext}
        actionsDisabled={feedbackActionsDisabled}
        modeSwitch={modeSwitch}
        onShare={shareResult}
        t={t}
        toggleGap={toggleGap}
        transcript={transcript}
        userId={user.userId}
        shareBusy={shareBusy}
        shareLink={shareLink}
        shareStatus={shareStatus}
        onCloseShareLink={closeShareLink}
        onCopyShareLink={copyShareLink}
      />
    );
  }

  return (
    <PracticeActiveView
      discardRecording={discardRecording}
      elapsed={elapsed}
      evalAnchorRef={evalAnchorRef}
      evalElapsed={evalElapsed}
      evaluate={evaluate}
      freeTopic={freeTopic}
      handleRecordClick={pressClick}
      handleRecordPressEnd={pressEnd}
      handleRecordPressStart={pressStart}
      hintGaps={hintGaps}
      hintAttemptId={hintAttemptId}
      hintBusy={hintBusy}
      hintCount={hintCount}
      hintError={hintError}
      mode={mode}
      modeSwitch={modeSwitch}
      onChangeTopic={handleNextFreeRound}
      onNoTopic={startNoTopic}
      pauseResumeRecording={pauseResumeCapture}
      pauseSupported={pauseSupported}
      paused={paused}
      pendingScenario={pendingScenario}
      phase={phase}
      revealNextHint={() => progressive.revealNextHint(session?._id)}
      round={round}
      scenario={scenario}
      session={session}
      startNewRound={startNewRound}
      startRecording={startRecording}
      stopRecording={stopCapture}
      streamingLen={streamingLen}
      t={t}
      transcriptionError={transcriptionError}
      transcript={transcript}
      setTranscript={setTranscript}
    />
  );
}
