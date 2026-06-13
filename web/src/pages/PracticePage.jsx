import { useState, useEffect, useRef, useCallback } from "react";
import { useParams } from "react-router-dom";
import { useUser } from "../context/UserContext.jsx";
import { api, correctStream } from "../api/client.js";
import { speak } from "../utils/tts.js";
import Icon from "../components/Icon.jsx";

const MAX_ROUNDS = 3;

const PROMPTS = {
  loading:    "准备场景中…",
  ready:      "进入情境，开口完成任务",
  recording:  "正在听…",
  review:     "看一眼，要不要让 AI 评？",
  evaluating: "AI 正在评你的表达…",
  feedback:   "",
};

function SpeakBtns({ text }) {
  if (!text) return null;
  return (
    <span className="spk-btns">
      <button className="spk-btn" title="播放" onClick={() => speak(text)}>🔊</button>
      <button className="spk-btn" title="慢速" onClick={() => speak(text, 0.75)}>🐢</button>
    </span>
  );
}

export default function PracticePage() {
  const { sessionId } = useParams();
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

  const recognitionRef = useRef(null);
  const timerRef = useRef(null);
  const secondsRef = useRef(0);
  const evalTimerRef = useRef(null);
  const sseControllerRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef(null);

  useEffect(() => {
    if (sessionId) {
      api.getSession(sessionId).then((s) => {
        setSession(s);
        setRound(Math.min((s.attempts?.length ?? 0) + 1, MAX_ROUNDS));
        setPhase("ready");
      }).catch(console.error);
      return;
    }
    startNewRound();
  }, [sessionId]);

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
    setElapsed("0:00");
    secondsRef.current = 0;
    setSession(null);
    audioChunksRef.current = null;
    try {
      const scenario = await api.nextScenario(user.userId);
      const sess = await api.createSession({
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
    setPhase("ready");
    window.scrollTo(0, 0);
  };

  const startRecording = useCallback(async () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      alert("请使用 Chrome 浏览器");
      return;
    }
    if (location.protocol === "http:" && location.hostname !== "localhost") {
      alert("当前是 HTTP 连接，Chrome 不允许使用麦克风。\n请用 HTTPS 访问，或在本地 localhost 调试。");
      return;
    }

    // 先清上一次录音
    audioChunksRef.current = null;

    const recognition = new SR();
    recognition.lang = "en-US";
    recognition.continuous = true;
    recognition.interimResults = true;

    let finalText = "";
    recognition.onresult = (event) => {
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) finalText += event.results[i][0].transcript + " ";
        else interim += event.results[i][0].transcript;
      }
      setTranscript(finalText + interim);
    };

    recognition.onerror = (event) => {
      setPhase("review");
      if (event.error === "not-allowed") {
        if (location.protocol === "http:") {
          alert("麦克风被浏览器拦截：当前是 HTTP 连接，Chrome 要求 HTTPS 才能使用麦克风。");
        } else {
          alert("麦克风权限被拒。Chrome 地址栏左侧锁图标 → 允许麦克风 → 刷新页面。");
        }
      } else if (event.error === "audio-capture") {
        alert("没检测到麦克风，检查一下设备连接。");
      } else if (event.error === "network") {
        alert("网络错误，检查一下网络。");
      }
    };
    recognition.onend = () => {
      clearInterval(timerRef.current);
      setPhase((p) => (p === "recording" ? "review" : p));
    };

    recognition.start();
    recognitionRef.current = recognition;
    secondsRef.current = 0;
    setElapsed("0:00");
    setTranscript("");
    setResult(null);
    setAutoSaved(0);
    setPhase("recording");

    // 同步启动 MediaRecorder 录音（失败不影响主流程）
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      const chunks = [];
      recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
      recorder.onstop = () => {
        audioChunksRef.current = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
        stream.getTracks().forEach((t) => t.stop());
      };
      recorder.start();
      mediaRecorderRef.current = recorder;
    } catch (err) {
      console.warn("MediaRecorder unavailable:", err);
    }

    timerRef.current = setInterval(() => {
      secondsRef.current += 1;
      const mm = Math.floor(secondsRef.current / 60);
      const ss = (secondsRef.current % 60).toString().padStart(2, "0");
      setElapsed(`${mm}:${ss}`);
    }, 1000);
  }, []);

  const stopRecording = () => {
    recognitionRef.current?.stop();
    recognitionRef.current = null;
    clearInterval(timerRef.current);
    mediaRecorderRef.current?.stop();
    mediaRecorderRef.current = null;
    setPhase("review");
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
        sessionId: session._id,
        text: transcript.trim(),
      },
      {
        onChunk: (text) => setStreamingLen((n) => n + text.length),
        onDone: ({ result: res, autoSaved: n, round: r }) => {
          clearInterval(evalTimerRef.current);
          setResult(res);
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

  const CAT_ZH = { grammar: "语法", naturalness: "自然度", vocabulary: "用词", register: "语体" };

  const scenario = session?.scenario;

  const ScenarioCard = () => (
    <div className="sc-card">
      <div className="sc-where">
        {scenario?.where || session?.topic || "场景"}
        {session?.isCustom && <span className="sc-custom-tag">为你定制</span>}
        <span className="sc-round-tag">第 {round} / {MAX_ROUNDS} 轮</span>
      </div>
      {scenario?.story && <p className="sc-story">{scenario.story}</p>}
      {scenario?.mission && <p className="sc-mission">🎯 {scenario.mission}</p>}
    </div>
  );

  if (phase === "feedback" && result) {
    const gaps = result.gaps ?? [];
    const progress = result.progress;
    const passed = progress?.verdict === "passed";
    const lastRound = round >= MAX_ROUNDS;

    return (
      <div className="practice-page fb-page fade-in">
        {session?.ossImageUrl && (
          <div className="fb-img">
            <img src={session.ossImageUrl} alt="scene" />
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
            {gaps.map((g, i) => (
              <div key={i} className="fb-gap-row">
                <div className="fb-gap-pair">
                  <span className="fb-gap-orig">{g.original}</span>
                  <span className="fb-gap-arrow">→</span>
                  <span className="fb-gap-better">{g.better}</span>
                  <SpeakBtns text={g.better} />
                  {g.category && <span className="fb-gap-cat">{CAT_ZH[g.category] ?? g.category}</span>}
                </div>
                {g.why && <p className="fb-gap-why">{g.why}</p>}
              </div>
            ))}
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
                <Icon name="refresh" size={16} />&nbsp;再说一遍（第 {round + 1} 轮）
              </button>
              <button className="su-btn su-btn-secondary" onClick={startNewRound} style={{ flex: 1, height: 48 }}>
                下一个&nbsp;<Icon name="next" size={16} />
              </button>
            </>
          )}
        </div>
        {!passed && lastRound && (
          <p className="fb-rounds-out">{MAX_ROUNDS} 轮到了，别恋战——这些表达已进复习，下个场景继续。</p>
        )}
      </div>
    );
  }

  return (
    <div className="practice-page">
      <div className={"su-img" + (phase === "loading" ? " loading" : "")}>
        {phase !== "loading" && session?.ossImageUrl && (
          <img src={session.ossImageUrl} alt="scene" />
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

      {(phase === "recording" || phase === "review" || phase === "evaluating") && (
        <div className={"su-transcript" + (!transcript ? " empty" : "")}>
          {transcript || "（说话内容会显示在这里）"}
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
