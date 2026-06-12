// 浏览器内置语音合成：播放地道说法（Phase 2 再换 CosyVoice）

let voice = null;

function pickVoice() {
  const vs = speechSynthesis.getVoices().filter((v) => v.lang.startsWith("en"));
  voice =
    vs.find((v) => v.name === "Samantha") ||
    vs.find((v) => v.name.includes("Google US")) ||
    vs.find((v) => v.lang === "en-US") ||
    vs[0] ||
    null;
}

if (typeof speechSynthesis !== "undefined") {
  speechSynthesis.onvoiceschanged = pickVoice;
  pickVoice();
}

export function speak(text, rate = 1.0) {
  if (typeof speechSynthesis === "undefined" || !text) return;
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  if (voice) u.voice = voice;
  u.lang = "en-US";
  u.rate = rate;
  speechSynthesis.speak(u);
}
