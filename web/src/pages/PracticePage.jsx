import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { useUser } from "../context/useUser.js";
import { useT } from "../i18n/useI18n.js";
import { api, correctStream, chatStream } from "../api/client.js";
import Icon from "../components/Icon.jsx";
import PracticePreferencePicker from "../components/PracticePreferencePicker.jsx";
import SpeakBtn from "../components/SpeakBtn.jsx";
import RecordingPlayer from "../components/RecordingPlayer.jsx";
import {
  getPracticePreferences,
  hasPracticePreferences,
  savePracticePreferences,
} from "../lib/practicePreferences.js";

const MAX_ROUNDS = 2;

// 去掉文本里的 emoji（旧场景数据的 where/points 可能带 emoji，统一不显示）
const stripEmoji = (s = "") =>
  s
    .replace(/[\u{1F000}-\u{1FAFF}]/gu, "")
    .replace(/[\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}]/gu, "")
    .replace(/[\u{FE00}-\u{FE0F}\u{200D}]/gu, "")
    .replace(/^[\s·•・]+/, "")
    .replace(/\s{2,}/g, " ")
    .trim();

function SpeakBtns({ text, practiceId }) {
  return <SpeakBtn text={text} practiceId={practiceId} />;
}

// 按句拆分 native 版，每句一行更清晰
const splitSentences = (s = "") =>
  s.match(/[^.!?]+[.!?]*/g)?.map((x) => x.trim()).filter(Boolean) ?? [s];

function ScoreBadge({ score }) {
  const t = useT();
  if (score == null) return null;
  return (
    <div className="fb-score">
      <span className="fb-score-num">{Number(score).toFixed(1)}</span>
      <span className="fb-score-unit">/ 9.0</span>
      <span className="fb-score-cap">{t("practice.ieltsBand")}</span>
    </div>
  );
}

function ScenarioCard({ scenario, topic, t }) {
  const points = scenario?.points ?? [];
  const where = stripEmoji(scenario?.where || topic || t("practice.scene_default"));
  return (
    <div className="sc-card">
      <div className="sc-grid">
        <div className="sc-k">{t("practice.place")}</div>
        <div className="sc-v sc-v-where">{where}</div>

        {scenario?.story && <>
          <div className="sc-k">{t("practice.scene")}</div>
          <div className="sc-v">{stripEmoji(scenario.story)}</div>
        </>}

        <div className="sc-k say">{t("practice.goal")}</div>
        <div className="sc-v say">
          {points.length > 0 ? (
            <ul className="sc-points">
              {points.map((p, i) => <li key={i}>{stripEmoji(p)}</li>)}
            </ul>
          ) : (
            <span className="sc-say-text">{stripEmoji(scenario?.mission || "")}</span>
          )}
        </div>
      </div>
    </div>
  );
}

function preferenceNoticeKey(match) {
  if (match === "relaxedDifficulty") return "practicePrefs.matchRelaxedDifficulty";
  if (match === "relaxedPurpose") return "practicePrefs.matchRelaxedPurpose";
  if (match === "fallback") return "practicePrefs.matchFallback";
  return "";
}

export default function PracticePage() {
  const { practiceId } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
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
    setSearchParams({}, { replace: true });   // 离开结果态，清掉 URL 标记
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
          setResult(res);
          // AI 自动收录的 gap 回传了 reviewItemId，用它初始化收录态（这样「已在错题本」可直接取消）
          const init = {};
          (res.gaps ?? []).forEach((g, i) => { if (g.reviewItemId) init[i] = g.reviewItemId; });
          setSavedMap(init);
          setAutoSaved(n);
          if (r) setRound(r);
          setChat([]);
          setPhase("feedback");
          // URL 标记结果态，刷新能恢复到这一页（见 load effect 的 ?result 分支）
          setSearchParams({ result: "1" }, { replace: true });
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

    // 全平台统一走 MediaRecorder + 后端 ASR：
    // 浏览器自带的 Web Speech API 走 Google 服务，国内不通；
    // 改成录完整段音频上传到 /api/transcribe 由 DashScope 转写。
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
          const { text: txt } = await api.transcribeAudio(user.userId, blob);
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
      recorder.start();
      mediaRecorderRef.current = recorder;
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
    mediaRecorderRef.current?.stop();
    mediaRecorderRef.current = null;
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
          <div className="pref-rhythm" aria-hidden="true">
            {Array.from({ length: 8 }).map((_, i) => <span key={i} />)}
          </div>
          <div className="pref-hero-main">
            <div className="eyebrow">{t("practicePrefs.eyebrow")}</div>
            <h1>{t("practicePrefs.welcomeTitle")}</h1>
            <p>{t("practicePrefs.welcomeSub")}</p>
          </div>
          <div className="pref-steps">
            <div className="pref-step"><span className="pref-step-num">1</span>{t("practicePrefs.welcomeStep1")}</div>
            <div className="pref-step"><span className="pref-step-num">2</span>{t("practicePrefs.welcomeStep2")}</div>
            <div className="pref-step"><span className="pref-step-num">3</span>{t("practicePrefs.welcomeStep3")}</div>
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
    const gaps = result.gaps ?? [];
    const progress = result.progress;
    const passed = progress?.verdict === "passed";
    const lastRound = round >= MAX_ROUNDS;

    return (
      <div className="practice-page fb-page fade-in">
        {session?.imageUrl && (
          <div className="fb-img">
            <img src={session.imageUrl} alt="scene" />
          </div>
        )}
        <ScenarioCard scenario={scenario} topic={session?.topic} t={t} />

        {recordingUrl && <RecordingPlayer src={recordingUrl} />}

        <ScoreBadge score={result.score} />

        {passed && <div className="fb-passed">{t("practice.soundedNative")}</div>}

        {progress && (
          <div className="fb-progress">
            {progress.comment && <p className="fb-progress-comment">{progress.comment}</p>}
            {progress.fixed?.length > 0 && (
              <div className="fb-progress-list fixed">
                <span className="label">{t("practice.usedThisTime")}</span>
                {progress.fixed.map((x, i) => <span key={i} className="chip">{x}</span>)}
              </div>
            )}
            {progress.remaining?.length > 0 && (
              <div className="fb-progress-list remaining">
                <span className="label">{t("practice.stillMissing")}</span>
                {progress.remaining.map((x, i) => <span key={i} className="chip">{x}</span>)}
              </div>
            )}
          </div>
        )}

        {transcript && (
          <div className="fb-transcript-card">
            <div className="fb-card-label">{t("practice.youSaid")}</div>
            <p className="fb-transcript-text">{transcript}</p>
          </div>
        )}

        {result.nativeVersion && (
          <div className="fb-native-card">
            <div className="fb-card-label native">{t("practice.nativeVersion")}<SpeakBtns text={result.nativeVersion} practiceId={session?._id} /></div>
            {splitSentences(result.nativeVersion).map((s, i) => (
              <p key={i} className="fb-native-text">{s}</p>
            ))}
          </div>
        )}

        {gaps.length > 0 && (
          <div className="fb-gaps-section">
            <div className="fb-section-label">{t("practice.gapsTitle", { n: gaps.length })}</div>
            {gaps.map((g, i) => {
              const added = Boolean(savedMap[i]);
              return (
                <div key={i} className="fb-gap-card">
                  <div className="fb-gap-head">
                    <span className="fb-gap-num">{i + 1}</span>
                    <button
                      className={"fb-gap-add" + (added ? " added" : "")}
                      onClick={() => toggleGap(g, i)}
                      title={added ? t("practice.removeTitle") : t("practice.addTitle")}
                    >
                      {added
                        ? <><Icon name="check" size={14} />&nbsp;{t("practice.inReview")}</>
                        : <><Icon name="plus" size={14} />&nbsp;{t("practice.addToReview")}</>}
                    </button>
                  </div>
                  <div className="fb-gap-table">
                    <div className="fb-gap-line is-said">
                      <span className="fb-gap-tag">{t("practice.gapYouSaid")}</span>
                      <span className="fb-gap-said">{g.original}</span>
                    </div>
                    <div className="fb-gap-line is-fix">
                      <span className="fb-gap-tag">{t("practice.gapSayThis")}</span>
                      <span className="fb-gap-fix">{g.better}</span>
                      <SpeakBtns text={g.better} practiceId={session?._id} />
                    </div>
                    {g.why && (
                      <div className="fb-gap-line">
                        <span className="fb-gap-tag">{t("practice.gapWhy")}</span>
                        <span className="fb-gap-whytext">{g.why}</span>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {autoSaved > 0 && (
          <p className="fb-autosaved">{t("practice.autoSaved", { n: autoSaved })}</p>
        )}

        <div className="fb-chat">
          <div className="fb-section-label">{t("practice.askTheCoach")}</div>
          {chat.map((m, i) => (
            <div key={i} className={"fb-chat-msg " + m.role}>
              {m.content || (chatBusy && i === chat.length - 1 ? <span className="fb-chat-typing">{t("practice.thinking")}</span> : "")}
            </div>
          ))}
          <div className="fb-chat-input">
            <textarea
              rows={1}
              value={chatInput}
              placeholder={t("practice.chatPlaceholder")}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); } }}
              disabled={chatBusy}
            />
            <button className="su-btn su-btn-primary" onClick={sendChat} disabled={chatBusy || !chatInput.trim()}>
              <Icon name="next" size={16} />
            </button>
          </div>
        </div>

        <div className="actions-row" style={{ marginTop: 8 }}>
          {passed || lastRound ? (
            <button className="su-btn su-btn-primary" onClick={() => startNewRound(session?.scenarioId)} style={{ flex: 1, height: 48 }}>
              {t("practice.nextScenario")}&nbsp;<Icon name="next" size={16} />
            </button>
          ) : (
            <>
              <button className="su-btn su-btn-primary" onClick={retrySame} style={{ flex: 2, height: 48 }}>
                <Icon name="refresh" size={16} />&nbsp;{t("practice.sayItAgain")}
              </button>
              <button className="su-btn su-btn-secondary" onClick={() => startNewRound(session?.scenarioId)} style={{ flex: 1, height: 48 }}>
                {t("practice.next")}&nbsp;<Icon name="next" size={16} />
              </button>
            </>
          )}
        </div>
        {!passed && lastRound && (
          <p className="fb-rounds-out">{t("practice.roundsOut")}</p>
        )}
      </div>
    );
  }

  return (
    <div className="practice-page">
      <div className={"su-img" + (phase === "loading" ? " loading" : "")}>
        {phase !== "loading" && session?.imageUrl && (
          <img src={session.imageUrl} alt="scene" />
        )}
      </div>

      {phase !== "loading" && <ScenarioCard scenario={scenario} topic={session?.topic} t={t} />}

      {phase !== "loading" && preferenceNoticeKey(session?.preferenceMatch) && (
        <div className="pref-match-note">
          {t(preferenceNoticeKey(session.preferenceMatch))}
        </div>
      )}

      {hintGaps.length > 0 && phase !== "loading" && (
        <div className="sc-hintbar">
          💡 {t("practice.tryToUse")}
          {hintGaps.map((g, i) => (
            <span key={i} className="sc-hint-item"><b>{g.better}</b><SpeakBtns text={g.better} practiceId={session?._id} /></span>
          ))}
        </div>
      )}

      <p className="su-prompt">{PROMPTS[phase]}</p>

      {(phase === "recording" || phase === "transcribing" || phase === "review" || phase === "evaluating") && (
        <div className={"su-transcript" + (!transcript ? " empty" : "")}>
          {transcript ||
            (phase === "recording"
              ? t("practice.willTranscribe")
              : phase === "transcribing"
              ? t("practice.transcribingDots")
              : t("practice.yourWordsHere"))}
          {phase === "recording" && <span className="live-dot" />}
        </div>
      )}

      {phase === "recording" && (
        <div className="su-rec-meta">
          <span className="rec-dot">{t("practice.rec")}</span>
          <span className="elapsed">{elapsed}</span>
        </div>
      )}

      <div style={{ height: phase === "review" || phase === "evaluating" ? 18 : 30 }} />

      {(phase === "loading" || phase === "ready") && (
        <div className="su-rec-wrap">
          <button
            className="su-rec"
            onPointerDown={() => handleRecordPressStart(startRecording)}
            onPointerUp={handleRecordPressEnd}
            onPointerLeave={handleRecordPressEnd}
            onContextMenu={(e) => e.preventDefault()}
            onClick={() => handleRecordClick(startRecording)}
            disabled={phase === "loading"}
          >
            <Icon name="mic" size={32} color="#fff" />
          </button>
          <div className="su-rec-label">{t("practice.tapToStart")}</div>
          <div className="su-rec-hint">{t("practice.tapHint")}</div>
          {phase === "ready" && session?.scenarioId && (
            <button
              className="su-skip"
              title={t("practice.tryAnother")}
              onClick={() => startNewRound(session.scenarioId)}
            >
              <Icon name="refresh" size={16} />
              <span>{t("practice.tryAnother")}</span>
            </button>
          )}
        </div>
      )}

      {phase === "recording" && (
        <div className="su-rec-wrap">
          <button
            className="su-rec recording"
            onPointerDown={() => handleRecordPressStart(stopRecording)}
            onPointerUp={handleRecordPressEnd}
            onPointerLeave={handleRecordPressEnd}
            onContextMenu={(e) => e.preventDefault()}
            onClick={() => handleRecordClick(stopRecording)}
          >
            <Icon name="stop" size={28} color="#fff" />
          </button>
          <div className="su-rec-label">{t("practice.tapToStop")}</div>
          <div className="su-rec-hint">{t("practice.stopHint")}</div>
        </div>
      )}

      {phase === "transcribing" && (
        <div className="su-rec-wrap">
          <button className="su-rec recording" disabled style={{ opacity: 0.6 }}>
            <span className="spin" />
          </button>
          <div className="su-rec-label">{t("practice.transcribingShort")}</div>
        </div>
      )}

      {phase === "review" && (
        <div className="actions-row">
          <button className="su-btn su-btn-secondary" style={{ flex: 1 }} onClick={startRecording}>
            <Icon name="refresh" size={16} />&nbsp;{t("practice.redo")}
          </button>
          <button className="su-btn su-btn-primary" style={{ flex: 2 }} onClick={() => evaluate()} disabled={!transcript.trim()}>
            {t("practice.getFeedback")}
          </button>
        </div>
      )}

      {phase === "evaluating" && (
        <>
          <div className="actions-row">
            <button className="su-btn su-btn-secondary" disabled style={{ flex: 1, opacity: 0.5 }}>
              <Icon name="refresh" size={16} />&nbsp;{t("practice.redo")}
            </button>
            <button className="su-btn su-btn-primary disabled" style={{ flex: 2 }}>
              <span className="spin" />&nbsp;{t("practice.aiReviewing")} {evalElapsed > 0 && <span style={{ marginLeft: 4, opacity: 0.8 }}>({evalElapsed}s)</span>}
            </button>
          </div>
          <p ref={evalAnchorRef} style={{
            fontFamily: "var(--ff-cn)", fontSize: 12, color: "var(--ink-3)",
            textAlign: "center", marginTop: 14, lineHeight: 1.6,
          }}>
            {streamingLen > 0
              ? t("practice.writingChars", { n: streamingLen })
              : evalElapsed < 15
              ? t("practice.checkingTask")
              : evalElapsed < 40
              ? t("practice.comparingNative")
              : t("practice.takingLonger")}
          </p>
        </>
      )}
    </div>
  );
}
