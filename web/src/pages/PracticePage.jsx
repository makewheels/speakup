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
  const [practicePrefs, setPracticePrefs] = useState(() => getPracticePreferences(user.userId));
  const [needsPrefs, setNeedsPrefs] = useState(
    () => !practiceId && mode !== "free" && !hasPracticePreferences(user.userId),
  );
  const [transcript, setTranscript] = useState("");
  const [transcriptionError, setTranscriptionError] = useState(false);
  const [elapsed, setElapsed] = useState("0:00");
  const [result, setResult] = useState(null);
  // 错题本收录：gap 作为错题收录；好表达笔记从结果文字中手动选中添加
  const {
    savedMap, setSavedMap, resetReviewCollection, toggleGap,
  } = useReviewCollection(session, result);
  const [autoSaved, setAutoSaved] = useState(0);
  const [round, setRound] = useState(1);
  const { resetShare, shareBusy, shareResult, shareStatus } = useResultShare({
    result, round, session, setSession, t, userId: user.userId,
  });
  const [hintGaps, setHintGaps] = useState([]);
  const [evalElapsed, setEvalElapsed] = useState(0);
  const [streamingLen, setStreamingLen] = useState(0);
  const [feedbackActionsDisabled, setFeedbackActionsDisabled] = useState(false);
  const [recordingUrl, setRecordingUrl] = useState(""); // 本次录音的本地 object URL，结果页回放用
  // 追问教练对话（流式）：question 从输入框取，错误文案用 i18n 在调用处拼
  const { chat, chatInput, setChatInput, chatBusy, sendChat: sendChatStream, resetChat } =
    useFollowupChat(user.userId, session?._id);
  const [paused, setPaused] = useState(false);           // 录音暂停中
  const [pauseSupported, setPauseSupported] = useState(false); // 浏览器 MediaRecorder 是否支持 pause

  const timerRef = useRef(null);
  const secondsRef = useRef(0);
  const evalTimerRef = useRef(null);
  const evalAnchorRef = useRef(null);
  const sseControllerRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef(null);
  const stoppingRef = useRef(false);
  const pausedRef = useRef(false);     // interval 回调里读，避免闭包拿旧 state
  const discardRef = useRef(false);    // 重录丢弃本次录音：onstop 里据此跳过转写/评估

  const hasUsableFeedback = (res) =>
    Boolean(
      (res?.nativeVersion || "").trim()
      || (res?.standardAnswer || "").trim()
      || (res?.gaps ?? []).length > 0,
    );

  // 本会话「看过但跳过」的 scenarioId（sessionStorage 跨刷新保留，不串号到其他用户）
  const skipKey = `skipped:${user.userId}`;
  const readSkipped = () => {
    try { return JSON.parse(sessionStorage.getItem(skipKey) || "[]"); } catch { return []; }
  };
  const writeSkipped = (arr) => sessionStorage.setItem(skipKey, JSON.stringify(arr));

  // 一轮新练习的公共状态重置（场景题 / 自由说共用）
  const resetRoundState = () => {
    setPhase("loading");
    setResult(null);
    setTranscript("");
    setTranscriptionError(false);
    setAutoSaved(0);
    resetShare();
    setRound(1);
    setHintGaps([]);
    resetReviewCollection();
    setElapsed("0:00");
    secondsRef.current = 0;
    setSession(null);
    audioChunksRef.current = null;
    setRecordingUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return ""; });
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
          setResult({
            summary: last.summary,
            nativeVersion: last.nativeVersion,
            standardAnswer: last.standardAnswer ?? "",
            note: last.note ?? "",
            noteChinese: last.noteChinese ?? "",
            score: last.score,
            gaps: last.gaps ?? [],
            progress: last.progress ?? null,
          });
          setTranscript(last.transcript ?? "");
          if (last.recordingUrl) setRecordingUrl(last.recordingUrl);  // 用户原声从 OSS 还原，刷新后可回放
          const init = {};
          (last.gaps ?? []).forEach((g, i) => { if (g.reviewItemId) init[i] = g.reviewItemId; });
          setSavedMap(init);
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

  // 组件卸载时取消 SSE 和 MediaRecorder
  useEffect(() => () => {
    sseControllerRef.current?.abort();
    mediaRecorderRef.current?.stop();
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
    setPhase("evaluating");
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
            setPhase("review");
            return;
          }
          setResult(res);
          // AI 自动收录的 gap 回传了 reviewItemId，用它初始化收录态（这样「已在错题本」可直接取消）
          const init = {};
          (res.gaps ?? []).forEach((g, i) => { if (g.reviewItemId) init[i] = g.reviewItemId; });
          setSavedMap(init);
          setAutoSaved(n);
          if (r) setRound(r);
          resetChat();
          setPhase("feedback");
          // 结果页的滚动定位由 PracticeFeedbackView 挂载时锚到雅思分数（Next 天然在屏外防误触）
          setFeedbackActionsDisabled(true);
          setTimeout(() => setFeedbackActionsDisabled(false), 1500);
          // URL 标记结果态，刷新能恢复到这一页（见 load effect 的 ?result 分支）
          // 必须用 navigate 显式带 pathname：setSearchParams 在当前 react-router 版本下会丢掉
          // pathname 使 useParams 的 practiceId 变空，触发 useEffect 走"无 practiceId"分支自动跳下一题
          navigate(`/practice/${active._id}?result=1`, { replace: true });
          // 评估完成后异步上传录音，关联到本轮 attempt（失败静默忽略）
          if (audioChunksRef.current && active?._id) {
            api.uploadRecording(active._id, user.userId, audioChunksRef.current, (r ?? round) - 1)
              .catch(console.warn);
            audioChunksRef.current = null;
          }
        },
        onError: (err) => {
          clearInterval(evalTimerRef.current);
          alert(t("practice.feedbackFailed", { msg: err.message }));
          setPhase("review");
        },
      }
    );
  }

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

    // 先清上一次录音
    audioChunksRef.current = null;
    setRecordingUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return ""; });

    secondsRef.current = 0;
    setElapsed("0:00");
    setTranscript("");
    setTranscriptionError(false);
    setResult(null);
    setAutoSaved(0);
    setPaused(false);
    pausedRef.current = false;
    discardRef.current = false;
    setPhase("recording");

    // 全平台统一走 MediaRecorder + 后端 DashScope Qwen ASR。
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const preferred = ["audio/mp4", "audio/webm;codecs=opus", "audio/webm", "audio/ogg"];
      const mimeType = preferred.find((tt) => MediaRecorder.isTypeSupported(tt));
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      setPauseSupported(typeof recorder.pause === "function");
      const chunks = [];
      recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
      recorder.onstop = async () => {
        const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
        stream.getTracks().forEach((tr) => tr.stop());
        clearInterval(timerRef.current);
        setPaused(false);
        pausedRef.current = false;
        if (discardRef.current) {
          // 「重录」触发的停止：关掉麦克风即可，不转写不评估，录音直接丢弃
          discardRef.current = false;
          return;
        }
        audioChunksRef.current = blob;
        setRecordingUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return URL.createObjectURL(blob); });
        setPhase("transcribing");
        try {
          // sess 而非 session state：自由说的会话是本次录音刚建的，闭包里 state 还是旧值
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
      recorder.start(1000);
      mediaRecorderRef.current = recorder;
      stoppingRef.current = false;
    } catch (err) {
      console.warn("MediaRecorder unavailable:", err);
      alert(t("practice.micFailed", { msg: err.message }));
      setPhase("ready");
      return;
    }

    timerRef.current = setInterval(() => {
      if (pausedRef.current) return; // 暂停期间计时冻结
      secondsRef.current += 1;
      const mm = Math.floor(secondsRef.current / 60);
      const ss = (secondsRef.current % 60).toString().padStart(2, "0");
      setElapsed(`${mm}:${ss}`);
    }, 1000);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, t, session, mode, freeTopic]);

  const stopRecording = () => {
    const recorder = mediaRecorderRef.current;
    if (!recorder || stoppingRef.current) return;
    stoppingRef.current = true;
    // 暂停态调 requestData 会抛 InvalidStateError——暂停时的数据本就已 flush，跳过即可
    try { recorder.requestData?.(); } catch { /* paused state: data already flushed */ }
    setTimeout(() => {
      if (mediaRecorderRef.current === recorder && recorder.state !== "inactive") {
        recorder.stop();
      }
      mediaRecorderRef.current = null;
      stoppingRef.current = false;
    }, 450);
    // setPhase 由 MediaRecorder.onstop 控制：transcribing → review
  };

  // 暂停 / 继续：MediaRecorder 原生支持，暂停段不进音频时间轴（拼出来仍是连续一段）
  const pauseResumeRecording = () => {
    const recorder = mediaRecorderRef.current;
    if (!recorder || recorder.state === "inactive") return;
    try {
      if (recorder.state === "paused") {
        recorder.resume();
        pausedRef.current = false;
        setPaused(false);
      } else {
        recorder.pause();
        pausedRef.current = true;
        setPaused(true);
      }
    } catch (err) {
      console.warn("MediaRecorder pause/resume failed:", err);
    }
  };

  // 重录：丢弃本次录音回到 ready，不转写不评估（onstop 里由 discardRef 短路）
  const discardRecording = () => {
    const recorder = mediaRecorderRef.current;
    if (!recorder || recorder.state === "inactive") return;
    discardRef.current = true;
    audioChunksRef.current = null;
    mediaRecorderRef.current = null;
    try { recorder.stop(); } catch { /* 已在停止中就算了 */ }
    clearInterval(timerRef.current);
    pausedRef.current = false;
    setPaused(false);
    secondsRef.current = 0;
    setElapsed("0:00");
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
      pauseResumeRecording={pauseResumeRecording}
      pauseSupported={pauseSupported}
      paused={paused}
      phase={phase}
      round={round}
      scenario={scenario}
      session={session}
      startNewRound={startNewRound}
      startRecording={startRecording}
      stopRecording={stopRecording}
      streamingLen={streamingLen}
      t={t}
      transcriptionError={transcriptionError}
      transcript={transcript}
      setTranscript={setTranscript}
    />
  );
}
