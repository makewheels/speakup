import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { useUser } from "../context/useUser.js";
import { useT } from "../i18n/useI18n.js";
import { api, correctStream, chatStream } from "../api/client.js";
import Icon from "../components/Icon.jsx";
import PracticePreferencePicker from "../components/PracticePreferencePicker.jsx";
import PracticeActiveView from "../components/practice/PracticeActiveView.jsx";
import PracticeFeedbackView from "../components/practice/PracticeFeedbackView.jsx";
import {
  getPracticePreferences,
  hasPracticePreferences,
  savePracticePreferences,
} from "../lib/practicePreferences.js";

const MAX_ROUNDS = 2;

export default function PracticePage() {
  const { practiceId } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { user } = useUser();
  const t = useT();

  // 阶段提示文案 —— 跟随语言切换，所以在组件内构造
  const PROMPTS = {
    loading:      t("practice.loading"),
    ready:        "",
    recording:    t("practice.listening"),
    transcribing: t("practice.transcribing"),
    review:       t("practice.review"),
    evaluating:   t("practice.evaluating"),
    feedback:     "",
  };

  const [session, setSession] = useState(null);
  const [phase, setPhase] = useState("loading");
  const [practicePrefs, setPracticePrefs] = useState(() => getPracticePreferences(user.userId));
  const [needsPrefs, setNeedsPrefs] = useState(() => !practiceId && !hasPracticePreferences(user.userId));
  const [transcript, setTranscript] = useState("");
  const [elapsed, setElapsed] = useState("0:00");
  const [result, setResult] = useState(null);
  const [autoSaved, setAutoSaved] = useState(0);
  const [round, setRound] = useState(1);
  const [hintGaps, setHintGaps] = useState([]);
  const [evalElapsed, setEvalElapsed] = useState(0);
  const [streamingLen, setStreamingLen] = useState(0);
  const [feedbackActionsDisabled, setFeedbackActionsDisabled] = useState(false);
  const [savedMap, setSavedMap] = useState({}); // gap 下标 -> reviewItem id（自动收录的初始就带，手动加/取消同步）
  const [recordingUrl, setRecordingUrl] = useState(""); // 本次录音的本地 object URL，结果页回放用
  const [chat, setChat] = useState([]);          // 追问对话 [{role, content}]
  const [chatInput, setChatInput] = useState("");
  const [chatBusy, setChatBusy] = useState(false);

  const chatControllerRef = useRef(null);

  const timerRef = useRef(null);
  const recordPressTimerRef = useRef(null);
  const recordPressHandledRef = useRef(false);
  const secondsRef = useRef(0);
  const evalTimerRef = useRef(null);
  const evalAnchorRef = useRef(null);
  const sseControllerRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef(null);
  const stoppingRef = useRef(false);

  const hasUsableFeedback = (res) =>
    Boolean((res?.nativeVersion || "").trim() || (res?.gaps ?? []).length > 0);

  // 本会话「看过但跳过」的 scenarioId（sessionStorage 跨刷新保留，不串号到其他用户）
  const skipKey = `skipped:${user.userId}`;
  const readSkipped = () => {
    try { return JSON.parse(sessionStorage.getItem(skipKey) || "[]"); } catch { return []; }
  };
  const writeSkipped = (arr) => sessionStorage.setItem(skipKey, JSON.stringify(arr));

  const startNewRound = async (extraSkip = null, overridePrefs = null) => {
    setPhase("loading");
    setResult(null);
    setTranscript("");
    setAutoSaved(0);
    setRound(1);
    setHintGaps([]);
    setSavedMap({});
    setElapsed("0:00");
    secondsRef.current = 0;
    setSession(null);
    audioChunksRef.current = null;
    setRecordingUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return ""; });
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

  useEffect(() => {
    // 已经在内存里加载好这道题（刚 startNewRound 后 navigate 改 URL 触发的回流）就别再拉
    if (practiceId && session?._id === practiceId) return;
    if (practiceId) {
      api.getPractice(practiceId).then((s) => {
        setSession(s);
        const attempts = s.attempts ?? [];
        // URL 带 ?result=1 且已有 attempt → 从最近一轮重建反馈视图（刷新不丢结果页）
        if (searchParams.get("result") && attempts.length > 0) {
          const last = attempts[attempts.length - 1];
          setResult({
            summary: last.summary,
            nativeVersion: last.nativeVersion,
            score: last.score,
            gaps: last.gaps ?? [],
            progress: last.progress ?? null,
          });
          setTranscript(last.transcript ?? "");
          if (last.recordingUrl) setRecordingUrl(last.recordingUrl);  // 用户原声从 OSS 还原，刷新后可回放
          const init = {};
          (last.gaps ?? []).forEach((g, i) => { if (g.reviewItemId) init[i] = g.reviewItemId; });
          setSavedMap(init);
          setRound(Math.min(attempts.length, MAX_ROUNDS));
          setChat(last.chat ?? []);
          setPhase("feedback");
        } else {
          setRound(Math.min(attempts.length + 1, MAX_ROUNDS));
          setPhase("ready");
        }
      }).catch(console.error);
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
    clearTimeout(recordPressTimerRef.current);
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

  // 同一场景再说一遍：保留 session，带着上一轮差距提示重录
  const retrySame = () => {
    setHintGaps((result?.gaps ?? []).filter((g) => g.better));
    setResult(null);
    setTranscript("");
    setAutoSaved(0);
    setRound((r) => Math.min(r + 1, MAX_ROUNDS));
    setSavedMap({});
    setPhase("ready");
    // 离开结果态，清掉 ?result 标记；同样用 navigate 显式带 pathname，避免 setSearchParams 丢 pathname 触发自动跳题
    if (session?._id) navigate(`/practice/${session._id}`, { replace: true });
    window.scrollTo(0, 0);
  };

  function evaluate(textOverride = null) {
    const text = (textOverride ?? transcript).trim();
    if (!text || !session) return;
    setPhase("evaluating");
    setEvalElapsed(0);
    setStreamingLen(0);
    evalTimerRef.current = setInterval(() => setEvalElapsed((s) => s + 1), 1000);

    sseControllerRef.current = correctStream(
      {
        userId: user.userId,
        practiceId: session._id,
        text,
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
          setChat([]);
          setPhase("feedback");
          // 结果页从顶部 AI 回复开始展示，Next 推到屏外防误触（对齐 retrySame）
          window.scrollTo(0, 0);
          setFeedbackActionsDisabled(true);
          setTimeout(() => setFeedbackActionsDisabled(false), 1500);
          // URL 标记结果态，刷新能恢复到这一页（见 load effect 的 ?result 分支）
          // 必须用 navigate 显式带 pathname：setSearchParams 在当前 react-router 版本下会丢掉
          // pathname 使 useParams 的 practiceId 变空，触发 useEffect 走"无 practiceId"分支自动跳下一题
          navigate(`/practice/${session._id}?result=1`, { replace: true });
          // 评估完成后异步上传录音，关联到本轮 attempt（失败静默忽略）
          if (audioChunksRef.current && session?._id) {
            api.uploadRecording(session._id, user.userId, audioChunksRef.current, (r ?? round) - 1)
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

  const startRecording = useCallback(async () => {
    if (location.protocol === "http:" && location.hostname !== "localhost") {
      alert(t("practice.needHttps"));
      return;
    }

    // 先清上一次录音
    audioChunksRef.current = null;
    setRecordingUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return ""; });

    secondsRef.current = 0;
    setElapsed("0:00");
    setTranscript("");
    setResult(null);
    setAutoSaved(0);
    setPhase("recording");

    // 全平台统一走 MediaRecorder + 后端 DashScope Qwen ASR。
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const preferred = ["audio/mp4", "audio/webm;codecs=opus", "audio/webm", "audio/ogg"];
      const mimeType = preferred.find((tt) => MediaRecorder.isTypeSupported(tt));
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      const chunks = [];
      recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
      recorder.onstop = async () => {
        const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
        audioChunksRef.current = blob;
        setRecordingUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return URL.createObjectURL(blob); });
        stream.getTracks().forEach((tr) => tr.stop());
        clearInterval(timerRef.current);
        setPhase("transcribing");
        try {
          const { text: txt } = await api.transcribeAudio(user.userId, blob, session?._id);
          setTranscript(txt || "");
          if ((txt || "").trim()) {
            evaluate(txt);
          } else {
            setPhase("review");
          }
        } catch (err) {
          alert(t("practice.transcriptionFailed", { msg: err.message }));
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
      secondsRef.current += 1;
      const mm = Math.floor(secondsRef.current / 60);
      const ss = (secondsRef.current % 60).toString().padStart(2, "0");
      setElapsed(`${mm}:${ss}`);
    }, 1000);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, t, session]);

  const stopRecording = () => {
    const recorder = mediaRecorderRef.current;
    if (!recorder || stoppingRef.current) return;
    stoppingRef.current = true;
    recorder.requestData?.();
    setTimeout(() => {
      if (mediaRecorderRef.current === recorder && recorder.state !== "inactive") {
        recorder.stop();
      }
      mediaRecorderRef.current = null;
      stoppingRef.current = false;
    }, 450);
    // setPhase 由 MediaRecorder.onstop 控制：transcribing → review
  };

  const handleRecordPressStart = (action) => {
    recordPressHandledRef.current = false;
    clearTimeout(recordPressTimerRef.current);
    recordPressTimerRef.current = setTimeout(() => {
      recordPressHandledRef.current = true;
      action();
    }, 320);
  };

  const handleRecordPressEnd = () => {
    clearTimeout(recordPressTimerRef.current);
  };

  const handleRecordClick = (action) => {
    if (recordPressHandledRef.current) {
      recordPressHandledRef.current = false;
      return;
    }
    action();
  };

  // 追问：基于本次反馈继续问 AI，流式追加到对话里
  const sendChat = () => {
    const q = chatInput.trim();
    if (!q || chatBusy || !session?._id) return;
    setChatInput("");
    // 先把用户问题和一个空的 assistant 占位推进去，流式往占位里填
    setChat((c) => [...c, { role: "user", content: q }, { role: "assistant", content: "" }]);
    setChatBusy(true);
    chatControllerRef.current = chatStream(
      { userId: user.userId, practiceId: session._id, question: q },
      {
        onChunk: (text) =>
          setChat((c) => {
            const next = [...c];
            next[next.length - 1] = { role: "assistant", content: next[next.length - 1].content + text };
            return next;
          }),
        onDone: () => setChatBusy(false),
        onError: (err) => {
          setChatBusy(false);
          setChat((c) => {
            const next = [...c];
            next[next.length - 1] = { role: "assistant", content: t("practice.chatError", { msg: err.message }) };
            return next;
          });
        },
      }
    );
  };

  // 收录 / 取消收录：点一下加入错题本，再点一下取消
  const toggleGap = async (g, i) => {
    if (!session?._id) return;
    const savedId = savedMap[i];
    if (savedId) {
      try {
        await api.deleteReviewItem(savedId, user.userId);
        setSavedMap((m) => { const n = { ...m }; delete n[i]; return n; });
      } catch (e) {
        alert(t("practice.removeFailed", { msg: e.message }));
      }
      return;
    }
    try {
      const { ids } = await api.addReviewItems(user.userId, [{
        expression: g.better,
        original: g.original,
        note: g.why,
        contextSentence: result?.nativeVersion || "",
        practiceId: session._id,
      }]);
      const id = ids?.[0];
      if (id) setSavedMap((m) => ({ ...m, [i]: id }));
    } catch (e) {
      alert(t("practice.addFailed", { msg: e.message }));
    }
  };

  const scenario = session?.scenario;

  if (needsPrefs) {
    return (
      <div className="practice-page pref-welcome fade-in">
        <div className="pref-hero">
          <div className="pref-hero-main">
            <h1>{t("practicePrefs.welcomeTitle")}</h1>
          </div>
        </div>

        <PracticePreferencePicker
          value={practicePrefs}
          onChange={setPracticePrefs}
          t={t}
        />

        <button className="su-btn su-btn-primary pref-start" onClick={startWithPreferences}>
          {t("practicePrefs.start")}
          <Icon name="next" size={16} />
        </button>
      </div>
    );
  }

  if (phase === "feedback" && result) {
    return (
      <PracticeFeedbackView
        autoSaved={autoSaved}
        chat={chat}
        chatBusy={chatBusy}
        chatInput={chatInput}
        maxRounds={MAX_ROUNDS}
        recordingUrl={recordingUrl}
        result={result}
        retrySame={retrySame}
        round={round}
        savedMap={savedMap}
        scenario={scenario}
        sendChat={sendChat}
        session={session}
        setChatInput={setChatInput}
        startNewRound={startNewRound}
        actionsDisabled={feedbackActionsDisabled}
        t={t}
        toggleGap={toggleGap}
        transcript={transcript}
      />
    );
  }

  return (
    <PracticeActiveView
      elapsed={elapsed}
      evalAnchorRef={evalAnchorRef}
      evalElapsed={evalElapsed}
      evaluate={evaluate}
      handleRecordClick={handleRecordClick}
      handleRecordPressEnd={handleRecordPressEnd}
      handleRecordPressStart={handleRecordPressStart}
      hintGaps={hintGaps}
      phase={phase}
      prompts={PROMPTS}
      scenario={scenario}
      session={session}
      startNewRound={startNewRound}
      startRecording={startRecording}
      stopRecording={stopRecording}
      streamingLen={streamingLen}
      t={t}
      transcript={transcript}
    />
  );
}
