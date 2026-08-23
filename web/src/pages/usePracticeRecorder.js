import { useCallback, useEffect, useRef, useState } from "react";

const PREFERRED_MIME_TYPES = ["audio/mp4", "audio/webm;codecs=opus", "audio/webm", "audio/ogg"];

function formatElapsed(totalSeconds) {
  const mm = Math.floor(totalSeconds / 60);
  const ss = (totalSeconds % 60).toString().padStart(2, "0");
  return `${mm}:${ss}`;
}

// 装配 MediaRecorder：选好 mimeType，收满 chunks，停止时回吐 blob
function buildMediaRecorder(stream, onStop) {
  const mimeType = PREFERRED_MIME_TYPES.find((tt) => MediaRecorder.isTypeSupported(tt));
  const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
  const chunks = [];
  recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
  recorder.onstop = () => onStop(new Blob(chunks, { type: recorder.mimeType || "audio/webm" }), stream);
  return recorder;
}

function togglePause(recorder, pausedRef, setPaused) {
  if (recorder.state === "paused") {
    recorder.resume();
    pausedRef.current = false;
    setPaused(false);
  } else {
    recorder.pause();
    pausedRef.current = true;
    setPaused(true);
  }
}

function startElapsedTimer({ timerRef, secondsRef, pausedRef, setElapsed }) {
  timerRef.current = setInterval(() => {
    if (pausedRef.current) return; // 暂停期间计时冻结
    secondsRef.current += 1;
    setElapsed(formatElapsed(secondsRef.current));
  }, 1000);
}

/**
 * MediaRecorder 录音机封装：计时、暂停、重录丢弃与本地回放 URL 都在这里，
 * 页面只关心「录完了拿 blob 去转写」。正常停止时调 onComplete，重录丢弃不调。
 */
export default function usePracticeRecorder() {
  const [elapsed, setElapsed] = useState("0:00");
  const [paused, setPaused] = useState(false);
  const [pauseSupported, setPauseSupported] = useState(false);
  const [recordingUrl, setRecordingUrl] = useState(""); // 本次录音的本地 object URL，结果页回放用

  const timerRef = useRef(null);
  const secondsRef = useRef(0);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef(null);
  const stoppingRef = useRef(false);
  const pausedRef = useRef(false);     // interval 回调里读，避免闭包拿旧 state
  const discardRef = useRef(false);    // 重录丢弃本次录音：onstop 里据此跳过回调
  const completeRef = useRef(null);    // 本次录音结束后的回调（转写入口）

  const releaseRecordingUrl = () => {
    setRecordingUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return ""; });
  };

  // 一轮新练习的录音侧重置（场景题 / 自由说共用）
  const resetCapture = () => {
    audioChunksRef.current = null;
    releaseRecordingUrl();
    secondsRef.current = 0;
    setElapsed("0:00");
  };

  // 组件卸载时停掉录音机
  useEffect(() => () => {
    mediaRecorderRef.current?.stop();
  }, []);

  // 从外部恢复回放地址（如刷新后从 OSS 还原用户原声）
  const restoreRecordingUrl = (url) => {
    setRecordingUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return url || ""; });
  };

  const handleRecorderStop = (blob, stream) => {
    stream.getTracks().forEach((tr) => tr.stop());
    clearInterval(timerRef.current);
    setPaused(false);
    pausedRef.current = false;
    if (discardRef.current) {
      // 「重录」触发的停止：关掉麦克风即可，不回调，录音直接丢弃
      discardRef.current = false;
      return;
    }
    audioChunksRef.current = blob;
    setRecordingUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return URL.createObjectURL(blob); });
    completeRef.current?.(blob);
  };

  const startCapture = useCallback(async ({ onComplete, onMicError } = {}) => {
    audioChunksRef.current = null;
    releaseRecordingUrl();
    secondsRef.current = 0;
    setElapsed("0:00");
    setPaused(false);
    pausedRef.current = false;
    discardRef.current = false;
    completeRef.current = onComplete ?? null;

    // 全平台统一走 MediaRecorder + 后端 DashScope Qwen ASR。
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = buildMediaRecorder(stream, handleRecorderStop);
      setPauseSupported(typeof recorder.pause === "function");
      recorder.start(1000);
      mediaRecorderRef.current = recorder;
      stoppingRef.current = false;
    } catch (err) {
      console.warn("MediaRecorder unavailable:", err);
      onMicError?.(err);
      return false;
    }

    startElapsedTimer({ timerRef, secondsRef, pausedRef, setElapsed });
    return true;
  }, []);

  const stopCapture = () => {
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
    // 后续流转由 MediaRecorder.onstop 控制
  };

  // 暂停 / 继续：MediaRecorder 原生支持，暂停段不进音频时间轴（拼出来仍是连续一段）
  const pauseResumeCapture = () => {
    const recorder = mediaRecorderRef.current;
    if (!recorder || recorder.state === "inactive") return;
    try {
      togglePause(recorder, pausedRef, setPaused);
    } catch (err) {
      console.warn("MediaRecorder pause/resume failed:", err);
    }
  };

  // 重录：丢弃本次录音（onstop 里由 discardRef 短路），返回是否真的丢弃了
  const discardCapture = () => {
    const recorder = mediaRecorderRef.current;
    if (!recorder || recorder.state === "inactive") return false;
    discardRef.current = true;
    audioChunksRef.current = null;
    mediaRecorderRef.current = null;
    try { recorder.stop(); } catch { /* 已在停止中就算了 */ }
    clearInterval(timerRef.current);
    pausedRef.current = false;
    setPaused(false);
    secondsRef.current = 0;
    setElapsed("0:00");
    return true;
  };

  // 取走录音 blob（上传用），取过即清空
  const takeAudioBlob = () => {
    const blob = audioChunksRef.current;
    audioChunksRef.current = null;
    return blob;
  };

  return {
    elapsed,
    paused,
    pauseSupported,
    recordingUrl,
    resetCapture,
    restoreRecordingUrl,
    startCapture,
    stopCapture,
    pauseResumeCapture,
    discardCapture,
    takeAudioBlob,
  };
}
