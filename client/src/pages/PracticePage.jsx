import { useState, useEffect, useRef, useCallback } from "react";
import { useParams } from "react-router-dom";
import { useUser } from "../context/UserContext.jsx";
import { api } from "../api/client.js";
import Icon from "../components/Icon.jsx";

const PROMPTS = {
  loading:    "准备图片中…",
  ready:      "看着图，用英语描述",
  recording:  "正在听…",
  review:     "看一眼，要不要让 AI 看？",
  evaluating: "AI 正在看你的描述…",
  feedback:   "",
};

export default function PracticePage() {
  const { sessionId } = useParams();
  const { user } = useUser();

  const [session, setSession] = useState(null);
  const [phase, setPhase] = useState("loading");      // loading | ready | recording | review | evaluating | feedback
  const [transcript, setTranscript] = useState("");
  const [elapsed, setElapsed] = useState("0:00");
  const [result, setResult] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [evalElapsed, setEvalElapsed] = useState(0);

  const recognitionRef = useRef(null);
  const timerRef = useRef(null);
  const secondsRef = useRef(0);
  const evalTimerRef = useRef(null);

  useEffect(() => {
    if (sessionId) {
      api.getSession(sessionId).then(setSession).catch(console.error);
      setPhase("ready");
      return;
    }
    startNewRound();
  }, [sessionId]);

  const startNewRound = async () => {
    setPhase("loading");
    setResult(null);
    setTranscript("");
    setSaved(false);
    setElapsed("0:00");
    secondsRef.current = 0;
    setSession(null);
    try {
      const image = await api.nextImage();
      const sess = await api.createSession({
        userId: user.userId,
        topic: image.topic,
        imageUrl: image.imageUrl,
      });
      setSession(sess);
      setPhase("ready");
    } catch (err) {
      alert("图片加载失败：" + err.message);
      setPhase("ready");
    }
  };

  const startRecording = useCallback(() => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      alert("请使用 Chrome 浏览器");
      return;
    }
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
        alert("麦克风权限被拒。Chrome 地址栏左侧锁图标 → 允许麦克风 → 刷新页面。");
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
    setSaved(false);
    setPhase("recording");

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
    setPhase("review");
  };

  const evaluate = async () => {
    if (!transcript.trim() || !session) return;
    setPhase("evaluating");
    setEvalElapsed(0);
    evalTimerRef.current = setInterval(() => setEvalElapsed((s) => s + 1), 1000);
    try {
      const data = await api.correct({
        userId: user.userId,
        sessionId: session._id,
        text: transcript.trim(),
        imageUrl: session.imageUrl || "",
      });
      setResult(data);
      setPhase("feedback");
    } catch {
      alert("评估请求失败");
      setPhase("review");
    } finally {
      clearInterval(evalTimerRef.current);
    }
  };

  const saveToReview = async () => {
    if (!result?.gaps?.length || !session) return;
    setSaving(true);
    try {
      const words = result.gaps.map((g) => ({
        word: g.better,
        original: g.original,
        note: g.why,
        contextSentence: result.nativeVersion || "",
        sessionId: session._id,
      }));
      await api.addVocabulary(user.userId, words);
      setSaved(true);
    } catch {
      alert("添加失败");
    } finally {
      setSaving(false);
    }
  };

  if (phase === "feedback" && result) {
    return (
      <div className="practice-page fb-page fade-in">
        <div className="scene-thumb">
          {session?.imageUrl && <img src={session.imageUrl} alt="scene" />}
          <div className="info">
            <div className="eyebrow">scene</div>
            <div className="topic">{session?.topic || "—"}</div>
            <div className="when">刚刚</div>
          </div>
        </div>

        {result.summary && (
          <div className="summary-card">
            <div className="eyebrow">summary</div>
            <p className="text">{result.summary}</p>
          </div>
        )}

        {transcript && (
          <section className="su-card you-card" style={{ marginBottom: 12 }}>
            <div className="card-eyebrow">
              <span className="eyebrow">你说的</span>
            </div>
            <div className="en">{transcript}</div>
          </section>
        )}

        {result.nativeVersion && (
          <section className="su-card native-card" style={{ marginBottom: 18 }}>
            <div className="card-eyebrow">
              <span className="eyebrow" style={{ color: "var(--accent)" }}>more native</span>
              <span className="chip accent">改写</span>
            </div>
            <div className="en">{result.nativeVersion}</div>
          </section>
        )}

        {result.gaps?.length > 0 && (
          <>
            <h3 className="section-title">
              差距点<span className="count">· {result.gaps.length} 处</span>
            </h3>
            <div style={{ marginBottom: 18 }}>
              {result.gaps.map((g, i) => (
                <div key={i} className="su-corr">
                  <div className="from">{g.original}</div>
                  <div className="arrow">→</div>
                  <div className="to">{g.better}</div>
                  <div className="reason">
                    {g.category && <span className="cat">{g.category}</span>}
                    {g.why}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}

        <div className="actions-stack">
          {result.gaps?.length > 0 && (
            <button
              className={"su-btn " + (saved ? "su-btn-tertiary" : "su-btn-primary")}
              disabled={saved || saving}
              onClick={saveToReview}
            >
              {saved ? (<><Icon name="check" size={18} />&nbsp;已添加到复习</>)
                : saving ? (<><span className="spin" />&nbsp;添加中…</>)
                : (<><Icon name="save" size={18} />&nbsp;添加到复习</>)}
            </button>
            )}
          <div className="actions-row">
            <button className="su-btn su-btn-secondary" onClick={() => { setResult(null); setTranscript(""); setPhase("ready"); setSaved(false); }} style={{ flex: 1, height: 48 }}>
              <Icon name="refresh" size={16} />&nbsp;重说
            </button>
            <button className="su-btn su-btn-secondary" onClick={startNewRound} style={{ flex: 1, height: 48 }}>
              下一张&nbsp;<Icon name="next" size={16} />
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="practice-page">
      <div className="topbar">
        <span className="scene-tag">{session?.topic ? `scene · ${session.topic}` : "scene"}</span>
      </div>

      <div className={"su-img" + (phase === "loading" ? " loading" : "")}>
        {phase !== "loading" && session?.imageUrl && (
          <img src={session.imageUrl} alt="scene" />
        )}
      </div>

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
              <span className="spin" />&nbsp;AI 正在看你的描述… {evalElapsed > 0 && <span style={{ marginLeft: 4, opacity: 0.8 }}>({evalElapsed}s)</span>}
            </button>
          </div>
          <p style={{
            fontFamily: "var(--ff-cn)", fontSize: 12, color: "var(--ink-3)",
            textAlign: "center", marginTop: 14, lineHeight: 1.6,
          }}>
            {evalElapsed < 15
              ? "正在让 AI 看图片..."
              : evalElapsed < 40
              ? "正在对比母语者会怎么说..."
              : evalElapsed < 75
              ? "图片有点慢，再等等..."
              : "比预期久。如果太久没结果可以试着重说。"}
          </p>
        </>
      )}
    </div>
  );
}
