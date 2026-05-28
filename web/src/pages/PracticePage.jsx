import { useState, useEffect, useRef, useCallback } from "react";
import { useParams } from "react-router-dom";
import { useUser } from "../context/UserContext.jsx";
import { api, correctStream } from "../api/client.js";
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
  const [phase, setPhase] = useState("loading");
  const [transcript, setTranscript] = useState("");
  const [elapsed, setElapsed] = useState("0:00");
  const [result, setResult] = useState(null);
  const [autoSaved, setAutoSaved] = useState(0);
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
      api.getSession(sessionId).then(setSession).catch(console.error);
      setPhase("ready");
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
    setElapsed("0:00");
    secondsRef.current = 0;
    setSession(null);
    audioChunksRef.current = null;
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
        imageUrl: session.imageUrl || "",
      },
      {
        onChunk: (text) => setStreamingLen((n) => n + text.length),
        onDone: ({ result: res, autoSaved: n }) => {
          clearInterval(evalTimerRef.current);
          setResult(res);
          setAutoSaved(n);
          setPhase("feedback");
          // 评估完成后异步上传录音（失败静默忽略）
          if (audioChunksRef.current && session?._id) {
            api.uploadRecording(session._id, user.userId, audioChunksRef.current)
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

  if (phase === "feedback" && result) {
    const gaps = result.gaps ?? [];
    const heroGap = gaps.find((g) => g.saveToReview) ?? gaps[0];
    const restGaps = heroGap ? gaps.filter((g) => g !== heroGap) : [];

    return (
      <div className="practice-page fb-page fade-in">
        <div className="su-img" style={{ marginBottom: 14 }}>
          {session?.imageUrl && <img src={session.imageUrl} alt="scene" />}
          {session?.topic && (
            <div className="caption">{session.topic}</div>
          )}
        </div>

        {result.summary && (
          <div className="summary-card">
            <p className="text">{result.summary}</p>
          </div>
        )}

        {heroGap && (
          <div className="hero-gap">
            <div className="eyebrow">今日重点</div>
            <div className="hero-better">{heroGap.better}</div>
            <div className="hero-original">你说的：{heroGap.original}</div>
            {heroGap.why && <div className="hero-why">{heroGap.why}</div>}
            {heroGap.example && <div className="hero-example">"{heroGap.example}"</div>}
          </div>
        )}

        {result.nativeVersion && (
          <section className="su-card native-card" style={{ marginBottom: 14 }}>
            <div className="card-eyebrow">
              <span className="eyebrow" style={{ color: "var(--accent)" }}>更地道的说法</span>
            </div>
            <div className="en">{result.nativeVersion}</div>
          </section>
        )}

        {restGaps.length > 0 && (
          <div className="rest-gaps">
            <div className="eyebrow" style={{ marginBottom: 8 }}>其他差距点</div>
            {restGaps.map((g, i) => (
              <div key={i} className="rest-gap-row">
                <div className="rest-gap-top">
                  <span className="rest-original">{g.original}</span>
                  <span className="rest-arrow">→</span>
                  <span className="rest-better">{g.better}</span>
                  {g.category && <span className="cat">{CAT_ZH[g.category] ?? g.category}</span>}
                </div>
                {g.why && <div className="rest-why">{g.why}</div>}
              </div>
            ))}
          </div>
        )}

        <div className="actions-stack">
          <div className="actions-row">
            <button
              className="su-btn su-btn-secondary"
              onClick={() => { setResult(null); setTranscript(""); setPhase("ready"); setAutoSaved(0); }}
              style={{ flex: 1, height: 48 }}
            >
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
            {streamingLen > 0
              ? `AI 正在写… 已生成 ${streamingLen} 字符`
              : evalElapsed < 15
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
