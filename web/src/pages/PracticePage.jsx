import { useState, useEffect, useRef, useCallback } from "react";
import { useParams } from "react-router-dom";
import { useUser } from "../context/UserContext.jsx";
import { api, correctStream } from "../api/client.js";
import { speak } from "../utils/tts.js";
import Icon from "../components/Icon.jsx";

const MAX_ROUNDS = 2;

const PROMPTS = {
  loading:    "准备场景中…",
  ready:      "",
  recording:  "正在听…",
  transcribing: "录音上传中，AI 正在转写…",
  review:     "看一眼，要不要让 AI 评？",
  evaluating: "AI 正在评你的表达…",
  feedback:   "",
};

// 去掉文本里的 emoji（旧场景数据的 where/points 可能带 emoji，统一不显示）
const stripEmoji = (s = "") =>
  s
    .replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{FE00}-\u{FE0F}\u{200D}]/gu, "")
    .replace(/^[\s·•・]+/, "")
    .replace(/\s{2,}/g, " ")
    .trim();

function SpeakBtns({ text }) {
  if (!text) return null;
  return (
    <span className="spk-btns">
      <button className="spk-btn" title="朗读" aria-label="朗读" onClick={() => speak(text)}>
        <Icon name="volume" size={16} />
      </button>
      <button className="spk-btn slow" title="慢速朗读" onClick={() => speak(text, 0.7)}>慢</button>
    </span>
  );
}

export default function PracticePage() {
  const { practiceId } = useParams();
  const { user } = useUser();

  const [session, setSession] = useState(null);
  const [phase, setPhase] = useState("loading");
  const [transcript, setTranscript] = useState("");
  const [elapsed, setElapsed] = useState("0:00");
  const [result, setResult] = useState(null);
  const [autoSaved, setAutoSaved] = useState(0);
  const [round, setRound] = useState(1);
  const [hintGaps, setHintGaps] = useState([]);
  const [evalElapsed, setEvalElapsed] = useState(0);
  const [streamingLen, setStreamingLen] = useState(0);
  const [savedIdx, setSavedIdx] = useState(() => new Set()); // 手动「+复习」过的 gap 下标

  const timerRef = useRef(null);
  const secondsRef = useRef(0);
  const evalTimerRef = useRef(null);
  const sseControllerRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef(null);

  useEffect(() => {
    if (practiceId) {
      api.getPractice(practiceId).then((s) => {
        setSession(s);
        setRound(Math.min((s.attempts?.length ?? 0) + 1, MAX_ROUNDS));
        setPhase("ready");
      }).catch(console.error);
      return;
    }
    startNewRound();
  }, [practiceId]);

  // 组件卸载时取消 SSE 和 MediaRecorder
  useEffect(() => () => {
    sseControllerRef.current?.abort();
    mediaRecorderRef.current?.stop();
  }, []);

  const startNewRound = async () => {
    setPhase("loading");
    setResult(null);
    setTranscript("");
    setAutoSaved(0);
    setRound(1);
    setHintGaps([]);
    setSavedIdx(new Set());
    setElapsed("0:00");
    secondsRef.current = 0;
    setSession(null);
    audioChunksRef.current = null;
    try {
      const scenario = await api.nextScenario(user.userId);
      const sess = await api.createPractice({
        userId: user.userId,
        scenarioId: scenario.scenarioId,
      });
      setSession({ ...sess, isCustom: scenario.isCustom });
      setPhase("ready");
    } catch (err) {
      alert("场景加载失败：" + err.message);
      setPhase("ready");
    }
  };

  // 同一场景再说一遍：保留 session，带着上一轮差距提示重录
  const retrySame = () => {
    setHintGaps((result?.gaps ?? []).filter((g) => g.better));
    setResult(null);
    setTranscript("");
    setAutoSaved(0);
    setRound((r) => Math.min(r + 1, MAX_ROUNDS));
    setSavedIdx(new Set());
    setPhase("ready");
    window.scrollTo(0, 0);
  };

  const startRecording = useCallback(async () => {
    if (location.protocol === "http:" && location.hostname !== "localhost") {
      alert("当前是 HTTP 连接，浏览器不允许使用麦克风。\n请用 HTTPS 访问。");
      return;
    }

    // 先清上一次录音
    audioChunksRef.current = null;

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
      const mimeType = preferred.find((t) => MediaRecorder.isTypeSupported(t));
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      const chunks = [];
      recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
      recorder.onstop = async () => {
        const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
        audioChunksRef.current = blob;
        stream.getTracks().forEach((t) => t.stop());
        clearInterval(timerRef.current);
        setPhase("transcribing");
        try {
          const { text } = await api.transcribeAudio(user.userId, blob);
          setTranscript(text || "");
          setPhase("review");
        } catch (err) {
          alert("语音识别失败：" + err.message);
          setPhase("review");
        }
      };
      recorder.start();
      mediaRecorderRef.current = recorder;
    } catch (err) {
      console.warn("MediaRecorder unavailable:", err);
      alert("无法访问麦克风：" + err.message);
      setPhase("ready");
      return;
    }

    timerRef.current = setInterval(() => {
      secondsRef.current += 1;
      const mm = Math.floor(secondsRef.current / 60);
      const ss = (secondsRef.current % 60).toString().padStart(2, "0");
      setElapsed(`${mm}:${ss}`);
    }, 1000);
  }, [user]);

  const stopRecording = () => {
    mediaRecorderRef.current?.stop();
    mediaRecorderRef.current = null;
    // setPhase 由 MediaRecorder.onstop 控制：transcribing → review
  };

  const evaluate = () => {
    if (!transcript.trim() || !session) return;
    setPhase("evaluating");
    setEvalElapsed(0);
    setStreamingLen(0);
    evalTimerRef.current = setInterval(() => setEvalElapsed((s) => s + 1), 1000);

    sseControllerRef.current = correctStream(
      {
        userId: user.userId,
        practiceId: session._id,
        text: transcript.trim(),
      },
      {
        onChunk: (text) => setStreamingLen((n) => n + text.length),
        onDone: ({ result: res, autoSaved: n, round: r }) => {
          clearInterval(evalTimerRef.current);
          setResult(res);
          setSavedIdx(new Set());
          setAutoSaved(n);
          if (r) setRound(r);
          setPhase("feedback");
          // 评估完成后异步上传录音，关联到本轮 attempt（失败静默忽略）
          if (audioChunksRef.current && session?._id) {
            api.uploadRecording(session._id, user.userId, audioChunksRef.current, (r ?? round) - 1)
              .catch(console.warn);
            audioChunksRef.current = null;
          }
        },
        onError: (err) => {
          clearInterval(evalTimerRef.current);
          alert("评估请求失败：" + err.message);
          setPhase("review");
        },
      }
    );
  };

  // 手动把某条差距加入复习本（AI 没自动收进去的，用户可自己加）
  const addGap = async (g, i) => {
    if (!session?._id || savedIdx.has(i)) return;
    try {
      await api.addReviewItems(user.userId, [{
        expression: g.better,
        original: g.original,
        note: g.why,
        contextSentence: result?.nativeVersion || "",
        practiceId: session._id,
      }]);
      setSavedIdx((prev) => new Set(prev).add(i));
    } catch (e) {
      alert("加入复习失败：" + e.message);
    }
  };

  const CAT_ZH = { grammar: "语法", naturalness: "自然度", vocabulary: "用词", register: "语体" };

  const scenario = session?.scenario;

  const ScenarioCard = () => {
    const points = scenario?.points ?? [];
    const where = stripEmoji(scenario?.where || session?.topic || "场景");
    return (
      <div className="sc-card">
        <div className="sc-grid">
          <div className="sc-k">地点</div>
          <div className="sc-v sc-v-where">{where}</div>

          {scenario?.story && <>
            <div className="sc-k">场景</div>
            <div className="sc-v">{stripEmoji(scenario.story)}</div>
          </>}

          <div className="sc-k say">要说</div>
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
  };

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
        <ScenarioCard />

        {passed && <div className="fb-passed">这轮说得地道了 ✓</div>}

        {progress && (
          <div className="fb-progress">
            {progress.comment && <p className="fb-progress-comment">{progress.comment}</p>}
            {progress.fixed?.length > 0 && (
              <div className="fb-progress-list fixed">
                <span className="label">✅ 这次用上了</span>
                {progress.fixed.map((x, i) => <span key={i} className="chip">{x}</span>)}
              </div>
            )}
            {progress.remaining?.length > 0 && (
              <div className="fb-progress-list remaining">
                <span className="label">⏳ 还没用上</span>
                {progress.remaining.map((x, i) => <span key={i} className="chip">{x}</span>)}
              </div>
            )}
          </div>
        )}

        {transcript && (
          <div className="fb-transcript-card">
            <div className="fb-card-label">你说的</div>
            <p className="fb-transcript-text">{transcript}</p>
          </div>
        )}

        {result.nativeVersion && (
          <div className="fb-native-card">
            <div className="fb-card-label native">Native 会这么说</div>
            <p className="fb-native-text">{result.nativeVersion}<SpeakBtns text={result.nativeVersion} /></p>
          </div>
        )}

        {result.summary && (
          <p className="fb-summary-line">{result.summary}</p>
        )}

        {gaps.length > 0 && (
          <div className="fb-gaps-section">
            <div className="fb-section-label">差距点 · {gaps.length} 处</div>
            {gaps.map((g, i) => {
              const added = savedIdx.has(i) || g.saveToReview;
              return (
                <div key={i} className="fb-gap-card">
                  <div className="fb-gap-head">
                    <span className="fb-gap-num">{i + 1}</span>
                    {g.category && <span className="fb-gap-cat">{CAT_ZH[g.category] ?? g.category}</span>}
                    <button
                      className={"fb-gap-add" + (added ? " added" : "")}
                      onClick={() => addGap(g, i)}
                      disabled={added}
                    >
                      {added
                        ? <><Icon name="check" size={13} />&nbsp;已加入复习</>
                        : <><Icon name="plus" size={13} />&nbsp;加入复习</>}
                    </button>
                  </div>
                  <div className="fb-gap-table">
                    <div className="fb-gap-line">
                      <span className="fb-gap-tag">我说的</span>
                      <span className="fb-gap-said">{g.original}</span>
                    </div>
                    <div className="fb-gap-line">
                      <span className="fb-gap-tag">应该说</span>
                      <span className="fb-gap-fix">{g.better}</span>
                      <SpeakBtns text={g.better} />
                    </div>
                    {g.why && (
                      <div className="fb-gap-line">
                        <span className="fb-gap-tag">为什么</span>
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
          <p className="fb-autosaved">已把 {autoSaved} 个表达放进复习</p>
        )}

        <div className="actions-row" style={{ marginTop: 8 }}>
          {passed || lastRound ? (
            <button className="su-btn su-btn-primary" onClick={startNewRound} style={{ flex: 1, height: 48 }}>
              下一个场景&nbsp;<Icon name="next" size={16} />
            </button>
          ) : (
            <>
              <button className="su-btn su-btn-primary" onClick={retrySame} style={{ flex: 2, height: 48 }}>
                <Icon name="refresh" size={16} />&nbsp;再说一遍
              </button>
              <button className="su-btn su-btn-secondary" onClick={startNewRound} style={{ flex: 1, height: 48 }}>
                下一个&nbsp;<Icon name="next" size={16} />
              </button>
            </>
          )}
        </div>
        {!passed && lastRound && (
          <p className="fb-rounds-out">这次也练过了——这些表达已进复习，下个场景继续。</p>
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

      {phase !== "loading" && <ScenarioCard />}

      {hintGaps.length > 0 && phase !== "loading" && (
        <div className="sc-hintbar">
          💡 这次试着用上：
          {hintGaps.map((g, i) => (
            <span key={i} className="sc-hint-item"><b>{g.better}</b><SpeakBtns text={g.better} /></span>
          ))}
        </div>
      )}

      <p className="su-prompt">{PROMPTS[phase]}</p>

      {(phase === "recording" || phase === "transcribing" || phase === "review" || phase === "evaluating") && (
        <div className={"su-transcript" + (!transcript ? " empty" : "")}>
          {transcript ||
            (phase === "recording"
              ? "（录完后会上传识别）"
              : phase === "transcribing"
              ? "（转写中…）"
              : "（说话内容会显示在这里）")}
          {phase === "recording" && <span className="live-dot" />}
        </div>
      )}

      {phase === "recording" && (
        <div className="su-rec-meta">
          <span className="rec-dot">● REC</span>
          <span className="elapsed">{elapsed}</span>
        </div>
      )}

      <div style={{ height: phase === "review" || phase === "evaluating" ? 18 : 30 }} />

      {(phase === "loading" || phase === "ready") && (
        <div className="su-rec-wrap">
          <button
            className="su-rec"
            onClick={startRecording}
            disabled={phase === "loading"}
          >
            <Icon name="mic" size={32} color="#fff" />
          </button>
          <div className="su-rec-label">点击开始</div>
        </div>
      )}

      {phase === "recording" && (
        <div className="su-rec-wrap">
          <button className="su-rec recording" onClick={stopRecording}>
            <Icon name="stop" size={28} color="#fff" />
          </button>
          <div className="su-rec-label">点击停止</div>
        </div>
      )}

      {phase === "transcribing" && (
        <div className="su-rec-wrap">
          <button className="su-rec recording" disabled style={{ opacity: 0.6 }}>
            <span className="spin" />
          </button>
          <div className="su-rec-label">转写中…</div>
        </div>
      )}

      {phase === "review" && (
        <div className="actions-row">
          <button className="su-btn su-btn-secondary" style={{ flex: 1 }} onClick={startRecording}>
            <Icon name="refresh" size={16} />&nbsp;重说
          </button>
          <button className="su-btn su-btn-primary" style={{ flex: 2 }} onClick={evaluate} disabled={!transcript.trim()}>
            让 AI 评估
          </button>
        </div>
      )}

      {phase === "evaluating" && (
        <>
          <div className="actions-row">
            <button className="su-btn su-btn-secondary" disabled style={{ flex: 1, opacity: 0.5 }}>
              <Icon name="refresh" size={16} />&nbsp;重说
            </button>
            <button className="su-btn su-btn-primary disabled" style={{ flex: 2 }}>
              <span className="spin" />&nbsp;AI 正在评你的表达… {evalElapsed > 0 && <span style={{ marginLeft: 4, opacity: 0.8 }}>({evalElapsed}s)</span>}
            </button>
          </div>
          <p style={{
            fontFamily: "var(--ff-cn)", fontSize: 12, color: "var(--ink-3)",
            textAlign: "center", marginTop: 14, lineHeight: 1.6,
          }}>
            {streamingLen > 0
              ? `AI 正在写… 已生成 ${streamingLen} 字符`
              : evalElapsed < 15
              ? "正在对照场景任务评估..."
              : evalElapsed < 40
              ? "正在对比母语者会怎么说..."
              : "比预期久。如果太久没结果可以试着重说。"}
          </p>
        </>
      )}
    </div>
  );
}
