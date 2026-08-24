import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { useUser } from "../context/useUser.js";
import { useT } from "../i18n/useI18n.js";
import { api, correctStream } from "../api/client.js";
import PracticeActiveView from "../components/practice/PracticeActiveView.jsx";
import PracticeFeedbackView from "../components/practice/PracticeFeedbackView.jsx";
import PracticeModeSwitch from "../components/practice/PracticeModeSwitch.jsx";
import PracticePrefsWelcome from "../components/practice/PracticePrefsWelcome.jsx";
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
import usePronunciationEvaluation, {
  EMPTY_FEEDBACK, hasUsableFeedback, resultFromAttempt, reviewMapFromGaps,
} from "./usePronunciationEvaluation.js";
import useResultShare from "./useResultShare.js";
import { track } from "../lib/analytics.js";

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
  const [practicePrefs, setPracticePrefs] = useState(() => getPracticePreferences(user.userId));
  const [needsPrefs, setNeedsPrefs] = useState(
    () => !practiceId && mode !== "free" && !hasPracticePreferences(user.userId),
  );
  const [transcript, setTranscript] = useState("");
  const [transcriptionError, setTranscriptionError] = useState(false);
  const [result, setResult] = useState(null);
  const [feedbackLoading, setFeedbackLoading] = useState(false);
  // 错题本收录：gap 作为错题收录；好表达笔记从结果文字中手动选中添加
  const {
    savedMap, setSavedMap, resetReviewCollection, toggleGap,
  } = useReviewCollection(session);
  const [autoSaved, setAutoSaved] = useState(0);
  const [round, setRound] = useState(1);
  const { resetShare, shareBusy, shareResult, shareStatus } = useResultShare({
    result, round, session, setSession, t, userId: user.userId,
  });
  const [hintGaps, setHintGaps] = useState([]);
  const [evalElapsed, setEvalElapsed] = useState(0);
  const [streamingLen, setStreamingLen] = useState(0);
  const [feedbackActionsDisabled, setFeedbackActionsDisabled] = useState(false);
  // 追问教练对话（流式）：question 从输入框取，错误文案用 i18n 在调用处拼
  const { chat, chatInput, setChatInput, chatBusy, sendChat: sendChatStream, resetChat } =
    useFollowupChat(user.userId, session?._id);
  const {
    elapsed, paused, pauseSupported, recordingUrl,
    resetCapture, restoreRecordingUrl, startCapture, stopCapture, pauseResumeCapture,
    discardCapture, takeAudioBlob,
  } = usePracticeRecorder();
  const {
    evaluateRecording, pronunciation, pronunciationLoading,
    resetPronunciation, restorePronunciation,
  } = usePronunciationEvaluation();

  const evalTimerRef = useRef(null);
  const evalAnchorRef = useRef(null);
  const sseControllerRef = useRef(null);

  const skipKey = `skipped:${user.userId}`;
  const readSkipped = () => {
    try { return JSON.parse(sessionStorage.getItem(skipKey) || "[]"); } catch { return []; }
  };
  const writeSkipped = (arr) => sessionStorage.setItem(skipKey, JSON.stringify(arr));

  // 一轮新练习的公共状态重置（场景题 / 自由说共用）
  const resetRoundState = () => {
    setPhase("loading");
    setResult(null);
    setFeedbackLoading(false);
    resetPronunciation();
    setTranscript("");
    setTranscriptionError(false);
    setAutoSaved(0);
    resetShare();
    setRound(1);
    setHintGaps([]);
    resetReviewCollection();
    resetCapture();
    setSession(null);
  };

  const startNewRound = async (extraSkip = null, overridePrefs = null) => {
    resetRoundState();
    clearTopic();
    let skipped = readSkipped();
    if (extraSkip && !skipped.includes(extraSkip)) {
      skipped = [...skipped, extraSkip];
      writeSkipped(skipped);
    }
    try {
      const activePrefs = overridePrefs || getPracticePreferences(user.userId);
      setPracticePrefs(activePrefs);
      const scenario = await api.nextScenario(user.userId, skipped, activePrefs);
      const sess = await api.createPractice({
        userId: user.userId,
        scenarioId: scenario.scenarioId,
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
        // 会话模式决定顶部切换器高亮与「下一个」行为（旧数据无 mode 按场景题）
        setMode(s?.mode === "free" ? "free" : "scenario");
        const attempts = s.attempts ?? [];
        // URL 带 ?result=1 且已有 attempt → 从最近一轮重建反馈视图（刷新不丢结果页）
        if (searchParams.get("result") && attempts.length > 0) {
          const last = attempts[attempts.length - 1];
          setResult(resultFromAttempt(last));
          setTranscript(last.transcript ?? "");
          restorePronunciation(last.pronunciation ?? null);
          if (last.recordingUrl) restoreRecordingUrl(last.recordingUrl);  // 用户原声从 OSS 还原，刷新后可回放
          setSavedMap(reviewMapFromGaps(last.gaps));
          setRound(attempts.length);
          resetChat(last.chat);
          setPhase("feedback");
        } else {
          setRound(attempts.length + 1);
          setPhase("ready");
        }
      }).catch(console.error);
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
    setResult(null);
    setFeedbackLoading(false);
    resetPronunciation();
    setTranscript("");
    setTranscriptionError(false);
    setAutoSaved(0);
    resetShare();
    setRound((r) => r + 1);
    resetReviewCollection();
    setPhase("ready");
    // 离开结果态，清掉 ?result 标记；同样用 navigate 显式带 pathname，避免 setSearchParams 丢 pathname 触发自动跳题
    if (session?._id) navigate(`/practice/${session._id}`, { replace: true });
    window.scrollTo(0, 0);
  };

  // sessOverride：自由说的会话是本次录音刚建的，onstop 闭包里 session state 还是旧值，显式传入
  function evaluate(textOverride = null, sessOverride = null) {
    const active = sessOverride || session;
    const text = (textOverride ?? transcript).trim();
    if (!text || !active) return;
    setResult(EMPTY_FEEDBACK);
    setFeedbackLoading(true);
    resetPronunciation();
    setPhase("feedback");
    navigate(`/practice/${active._id}?result=1`, { replace: true });
    setEvalElapsed(0);
    setStreamingLen(0);
    evalTimerRef.current = setInterval(() => setEvalElapsed((s) => s + 1), 1000);

    sseControllerRef.current = correctStream(
      {
        userId: user.userId,
        practiceId: active._id,
        text,
        // 自由说：不判任务完成度，后端据此走 FREE prompt；话题一并落 attempt
        mode: active.mode === "free" ? "free" : "scenario",
        freeTopic: active.freeTopic || "",
      },
      {
        onChunk: (chunk) => setStreamingLen((n) => n + chunk.length),
        onDone: ({ result: res, autoSaved: n, round: r }) => {
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
          track("practice_result", {
            mode: active.mode === "free" ? "free" : "scenario",
            score: res.score ?? null,
            gaps: (res.gaps ?? []).length,
            round: r ?? round,
            userId: user.userId,
          });
          // AI 自动收录的 gap 回传了 reviewItemId，用它初始化收录态（这样「已在错题本」可直接取消）
          setSavedMap(reviewMapFromGaps(res.gaps));
          setAutoSaved(n);
          if (r) setRound(r);
          resetChat();
          // 结果页首帧在绘制前回到顶部；后续流式完成和媒体加载不再重复滚动。
          setFeedbackActionsDisabled(true);
          setTimeout(() => setFeedbackActionsDisabled(false), 1500);
          // URL 标记结果态，刷新能恢复到这一页（见 load effect 的 ?result 分支）
          // 必须用 navigate 显式带 pathname：setSearchParams 在当前 react-router 版本下会丢掉
          // pathname 使 useParams 的 practiceId 变空，触发 useEffect 走"无 practiceId"分支自动跳下一题
          // 评估完成后异步上传录音，关联到本轮 attempt（失败静默忽略）
          const audioBlob = takeAudioBlob();
          if (audioBlob && active?._id) {
            const attemptIndex = (r ?? round) - 1;
            evaluateRecording({
              audioBlob, practiceId: active._id, userId: user.userId, attemptIndex,
            });
          }
        },
        onError: (err) => {
          clearInterval(evalTimerRef.current);
          alert(t("practice.feedbackFailed", { msg: err.message }));
          setFeedbackLoading(false);
          setResult(null);
          setPhase("review");
          navigate(`/practice/${active._id}`, { replace: true });
        },
      }
    );
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

    setTranscript("");
    setTranscriptionError(false);
    setResult(null);
    setAutoSaved(0);
    setPhase("recording");

    const started = await startCapture({
      onComplete: (blob) => transcribeAndEvaluate(blob, sess),
      onMicError: (err) => {
        alert(t("practice.micFailed", { msg: err.message }));
        setPhase("ready");
      },
    });
    if (started) track("practice_recording_started", { mode, userId: user.userId });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, t, session, mode, freeTopic, startCapture]);

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

  const scenario = session?.scenario;
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

  if (phase === "feedback" && result) {
    return (
      <PracticeFeedbackView
        autoSaved={autoSaved}
        chat={chat}
        chatBusy={chatBusy}
        chatInput={chatInput}
        recordingUrl={recordingUrl}
        result={result}
        loading={feedbackLoading}
        streamingLen={streamingLen}
        pronunciation={pronunciation}
        pronunciationLoading={pronunciationLoading}
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
        shareStatus={shareStatus}
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
      mode={mode}
      modeSwitch={modeSwitch}
      onChangeTopic={handleNextFreeRound}
      onNoTopic={startNoTopic}
      pauseResumeRecording={pauseResumeCapture}
      pauseSupported={pauseSupported}
      paused={paused}
      phase={phase}
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
