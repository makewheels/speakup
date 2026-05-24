import { useState, useEffect, useRef, useCallback } from "react";
import { useParams } from "react-router-dom";
import { useUser } from "../context/UserContext.jsx";
import { api } from "../api/client.js";

export default function PracticePage() {
  const { sessionId } = useParams();
  const { user } = useUser();

  const [session, setSession] = useState(null);
  const [loadingImage, setLoadingImage] = useState(!sessionId);
  const [recording, setRecording] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [result, setResult] = useState(null);
  const [correcting, setCorrecting] = useState(false);
  const [savingWords, setSavingWords] = useState(false);
  const [wordsSaved, setWordsSaved] = useState(false);
  const recognitionRef = useRef(null);

  // Load existing session (history view) or create new one
  useEffect(() => {
    if (sessionId) {
      api.getSession(sessionId).then(setSession).catch(console.error);
      return;
    }
    startNewRound();
  }, [sessionId]);

  const startNewRound = async () => {
    setLoadingImage(true);
    setResult(null);
    setTranscript("");
    setWordsSaved(false);
    setSession(null);
    try {
      const image = await api.nextImage(user.userId);
      const sess = await api.createSession({
        userId: user.userId,
        topic: image.topic,
        sceneDescription: image.prompt,
        imageUrl: image.imageUrl,
        imagePrompt: image.prompt,
      });
      setSession(sess);
    } catch (err) {
      alert("图片加载失败: " + err.message);
    } finally {
      setLoadingImage(false);
    }
  };

  const startRecording = useCallback(() => {
    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert("请使用 Chrome 浏览器");
      return;
    }
    const recognition = new SpeechRecognition();
    recognition.lang = "en-US";
    recognition.continuous = true;
    recognition.interimResults = true;

    let finalText = "";
    recognition.onresult = (event) => {
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) {
          finalText += event.results[i][0].transcript + " ";
        } else {
          interim += event.results[i][0].transcript;
        }
      }
      setTranscript(finalText + interim);
    };

    recognition.onerror = (event) => {
      setRecording(false);
      if (event.error === "not-allowed") {
        alert("麦克风被禁止了。请在浏览器地址栏左边点锁图标 → 允许麦克风权限，然后刷新页面。");
      } else if (event.error === "audio-capture") {
        alert("未检测到麦克风设备，请检查麦克风是否连接。");
      } else {
        console.error("Recognition error:", event.error);
      }
    };
    recognition.onend = () => setRecording(false);

    recognition.start();
    recognitionRef.current = recognition;
    setRecording(true);
    setTranscript("");
    setResult(null);
    setWordsSaved(false);
  }, []);

  const stopRecording = () => {
    recognitionRef.current?.stop();
    recognitionRef.current = null;
    setRecording(false);
  };

  const requestCorrection = async () => {
    if (!transcript.trim() || !session) return;
    setCorrecting(true);
    try {
      const data = await api.correct({
        userId: user.userId,
        sessionId: session._id,
        text: transcript.trim(),
        sceneDescription: session.sceneDescription || "",
        imageUrl: session.imageUrl || "",
      });
      setResult(data);
      // Prefetch next image while user reviews results
      api.prefetchImage(user.userId).catch(() => {});
      // Refresh session
      const updated = await api.getSession(session._id);
      setSession(updated);
    } catch {
      alert("纠正请求失败");
    } finally {
      setCorrecting(false);
    }
  };

  const saveToVocabulary = async () => {
    if (!result?.corrections?.length || !session) return;
    setSavingWords(true);
    try {
      const words = result.corrections.map((c) => ({
        word: c.corrected,
        chinese: c.reason || "",
        contextSentence: result.correctedText || "",
        sessionId: session._id,
      }));
      await api.addVocabulary(user.userId, words);
      setWordsSaved(true);
    } catch {
      alert("保存失败");
    } finally {
      setSavingWords(false);
    }
  };

  if (loadingImage) {
    return (
      <div className="practice-page">
        <div className="loading-image">
          <div className="spinner" />
          <p>正在为你准备练习图片...</p>
          <p className="loading-sub">AI 正在生成场景，请稍候</p>
        </div>
      </div>
    );
  }

  return (
    <div className="practice-page">
      {session?.imageUrl && (
        <img src={session.imageUrl} alt="Scene" className="scene-image" />
      )}

      {!result && (
        <>
          <div className="record-bar">
            <button
              className={`record-btn ${recording ? "recording" : ""}`}
              onClick={recording ? stopRecording : startRecording}
            >
              {recording ? "⏹ 停止录音" : "🎤 开始说英语"}
            </button>
          </div>

          {transcript && (
            <div className="transcript-box">
              <h3>你说的：</h3>
              <p>{transcript}</p>
              <div className="transcript-actions">
                <button
                  className="correct-btn"
                  onClick={requestCorrection}
                  disabled={correcting}
                >
                  {correcting ? "纠正中..." : "让 AI 纠正"}
                </button>
                <button className="edit-btn" onClick={startRecording}>
                  重说
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {result && (
        <div className="result-section">
          {result.whatISee && (
            <div className="result-block ai-see-block">
              <h3>AI sees in the image:</h3>
              <p>{result.whatISee}</p>
            </div>
          )}

          <div className="result-block">
            <h3>Your corrected version:</h3>
            <p className="corrected-text">{result.correctedText}</p>
          </div>

          {result.corrections?.length > 0 && (
            <div className="result-block">
              <h3>Corrections:</h3>
              <ul className="corrections-list">
                {result.corrections.map((c, i) => (
                  <li key={i}>
                    <span className="orig">{c.original}</span>
                    <span className="arrow">→</span>
                    <span className="corr">{c.corrected}</span>
                    <span className="reason">{c.reason}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {result.missedElements?.length > 0 && (
            <div className="result-block">
              <h3>You missed in the image:</h3>
              <ul>
                {result.missedElements.map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            </div>
          )}

          {result.suggestedVocabulary?.length > 0 && (
            <div className="result-block">
              <h3>Richer vocabulary to try:</h3>
              <ul className="vocab-suggestions">
                {result.suggestedVocabulary.map((v, i) => (
                  <li key={i}>{v}</li>
                ))}
              </ul>
            </div>
          )}

          {result.corrections?.length > 0 && !wordsSaved && (
            <button className="save-vocab-btn" onClick={saveToVocabulary} disabled={savingWords}>
              {savingWords ? "Saving..." : "Save to vocabulary"}
            </button>
          )}
          {wordsSaved && <p className="saved-msg">Saved!</p>}

          {result.tips?.length > 0 && (
            <div className="result-block tips-block">
              <h3>Study tips:</h3>
              <ul>
                {result.tips.map((t, i) => (
                  <li key={i}>{t}</li>
                ))}
              </ul>
            </div>
          )}

          <button className="new-round-btn" onClick={startNewRound}>
            Next image
          </button>
        </div>
      )}
    </div>
  );
}
