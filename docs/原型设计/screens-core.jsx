// SpeakUp · screens-core.jsx
// 4.1 Login · 4.2 Practice (4 states) · 4.3 Feedback

const { useState: useStateCore, useEffect: useEffectCore, useRef: useRefCore } = React;

// ─────────────────────────────────────────────────────────────
// 4.1 LOGIN
// ─────────────────────────────────────────────────────────────
function LoginScreen({ phone = "", state = "empty" }) {
  // state: 'empty' | 'typing' | 'submitting' | 'error'
  const valid = /^1\d{10}$/.test(phone);
  const showError = state === "error";
  const submitting = state === "submitting";

  return (
    <div className="su-screen">
      <div className="su-body" style={{ display: "flex", flexDirection: "column", padding: "0 28px" }}>
        {/* brand */}
        <div style={{ marginTop: 64, marginBottom: 56 }}>
          <div className="eyebrow" style={{ marginBottom: 14 }}>v0.1 · DEMO</div>
          <h1 className="serif" style={{ fontSize: 48, fontWeight: 400, lineHeight: 1.02, margin: 0, letterSpacing: "-0.025em" }}>
            SpeakUp
          </h1>
          <p style={{
            fontFamily: "var(--ff-cn)", fontSize: 15, color: "var(--ink-2)",
            margin: "14px 0 0", lineHeight: 1.55, maxWidth: 280, letterSpacing: 0,
          }}>
            看图片，用英语描述。<br/>
            AI 客观纠正不地道的表达。
          </p>
        </div>

        {/* phone field */}
        <label style={{ display: "block" }}>
          <div className="eyebrow" style={{ marginBottom: 10 }}>手机号</div>
          <div style={{
            display: "flex", alignItems: "center", gap: 10,
            borderBottom: showError ? "1px solid var(--warn)" : "1px solid var(--ink)",
            paddingBottom: 10,
          }}>
            <span className="mono" style={{ fontSize: 18, color: "var(--ink-2)" }}>+86</span>
            <div style={{
              flex: 1,
              fontFamily: "var(--ff-mono)", fontSize: 22, color: state === "empty" ? "var(--ink-4)" : "var(--ink)",
              letterSpacing: "0.04em", minHeight: 28,
            }}>
              {state === "empty" ? "138 0000 0000" : phone.replace(/(\d{3})(\d{4})(\d{0,4}).*/, (_, a, b, c) => c ? `${a} ${b} ${c}` : `${a} ${b}`)}
              {(state === "typing" || state === "error") && <span style={{
                display: "inline-block", width: 1.5, height: 22,
                background: "var(--ink)", marginLeft: 2, verticalAlign: -3,
                animation: "blink 1s step-end infinite",
              }} />}
            </div>
          </div>
          {showError && (
            <div style={{ fontFamily: "var(--ff-cn)", fontSize: 12, color: "var(--warn)", marginTop: 8, letterSpacing: 0 }}>
              手机号格式不对，请重新输入
            </div>
          )}
        </label>

        {/* hint */}
        <p style={{
          fontFamily: "var(--ff-cn)", fontSize: 12, color: "var(--ink-3)",
          marginTop: 18, lineHeight: 1.55, letterSpacing: 0,
        }}>
          输入手机号即注册，无需验证码。
        </p>

        <div style={{ flex: 1 }}></div>

        {/* submit */}
        <button className={"su-btn su-btn-primary" + (!valid && !submitting ? " disabled" : "")} disabled={!valid && !submitting} style={{ marginBottom: 22 }}>
          {submitting ? <><span className="spin"></span>&nbsp;进入</> : "进入"}
        </button>

        <p style={{
          fontFamily: "var(--ff-mono)", fontSize: 10, color: "var(--ink-3)",
          textAlign: "center", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 8,
        }}>
          please use chrome · 仅支持 chrome 浏览器
        </p>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// 4.2 PRACTICE — 4 sub-states + AI loading
// state: 'loading' | 'ready' | 'recording' | 'review' | 'evaluating'
// ─────────────────────────────────────────────────────────────
function PracticeScreen({ state = "ready", caption = "kitchen · morning", transcript = "", elapsed = "0:00", dueCount = 3 }) {
  return (
    <div className="su-screen">
      <NavBar title="" right={<span style={{ fontFamily: "var(--ff-mono)", fontSize: 11, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--ink-3)" }}>scene · 1 / ∞</span>} />

      <div className="su-body" style={{ paddingTop: 4 }}>
        {/* due reminder strip */}
        {dueCount > 0 && state === "ready" && (
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: "10px 14px", background: "var(--bg-mute)",
            border: "1px solid var(--rule)", borderRadius: 10, marginBottom: 16,
          }}>
            <span style={{ fontFamily: "var(--ff-cn)", fontSize: 13, color: "var(--ink-2)" }}>
              今天有 <strong style={{ color: "var(--ink)" }}>{dueCount}</strong> 个错题待复习
            </span>
            <span className="action-link">去复习</span>
          </div>
        )}

        {/* image */}
        <ImagePh
          caption={state === "loading" ? "准备图片中…" : caption}
          loading={state === "loading"}
        />

        {/* prompt */}
        <p style={{
          fontFamily: "var(--ff-cn)", fontSize: 13, color: "var(--ink-2)",
          textAlign: "center", margin: "18px 0 14px", letterSpacing: 0,
        }}>
          {state === "loading" ? "准备图片中…"
            : state === "ready" ? "看着图，用英语描述"
            : state === "recording" ? "正在听…"
            : state === "review" ? "看一眼，要不要让 AI 看？"
            : "AI 正在看你的描述…"}
        </p>

        {/* transcript */}
        {(state === "recording" || state === "review" || state === "evaluating") && (
          <div className={"su-transcript" + (!transcript ? " empty" : "")}>
            {transcript || "（说话内容会显示在这里）"}
            {state === "recording" && <span className="live-dot"></span>}
          </div>
        )}

        {/* timer (recording) */}
        {state === "recording" && (
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
            marginTop: 14,
          }}>
            <span className="mono" style={{ fontSize: 13, color: "var(--warn)", letterSpacing: "0.04em" }}>
              ● REC
            </span>
            <span className="mono" style={{ fontSize: 13, color: "var(--ink-2)" }}>{elapsed}</span>
          </div>
        )}

        {/* spacer */}
        <div style={{ height: state === "review" || state === "evaluating" ? 18 : 30 }}></div>

        {/* record CTA */}
        {(state === "ready" || state === "loading") && (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
            <button className="su-rec" disabled={state === "loading"} style={state === "loading" ? { opacity: 0.4 } : {}}>
              <Icon name="mic" size={32} color="#fff" stroke={1.6} />
            </button>
            <div className="su-rec-label">点击开始</div>
          </div>
        )}
        {state === "recording" && (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
            <button className="su-rec recording">
              <Icon name="stop" size={28} color="#fff" />
            </button>
            <div className="su-rec-label">点击停止</div>
          </div>
        )}

        {/* post-record actions */}
        {state === "review" && (
          <div style={{ display: "flex", gap: 10 }}>
            <button className="su-btn su-btn-secondary" style={{ flex: 1 }}>
              <Icon name="refresh" size={16} />&nbsp;重说
            </button>
            <button className="su-btn su-btn-primary" style={{ flex: 2 }}>
              让 AI 纠正
            </button>
          </div>
        )}
        {state === "evaluating" && (
          <div style={{ display: "flex", gap: 10 }}>
            <button className="su-btn su-btn-secondary" disabled style={{ flex: 1, opacity: 0.5 }}>
              <Icon name="refresh" size={16} />&nbsp;重说
            </button>
            <button className="su-btn su-btn-primary disabled" style={{ flex: 2 }}>
              <span className="spin"></span>&nbsp;AI 正在看你的描述…
            </button>
          </div>
        )}
      </div>

      <TabBar active="practice" dueCount={dueCount} />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// 4.3 FEEDBACK
// ─────────────────────────────────────────────────────────────
function FeedbackScreen({ saved = false, dueCount = 3 }) {
  const aiSees = "A bright kitchen in the morning. A young woman in a striped apron is making coffee, with sunlight streaming in through the window above the sink.";
  const userSaid = "There is a woman. She is make coffee in the kitchen. The kitchen have many sunlight and there is some peoples outside maybe.";
  const native = "A woman is making coffee in a sunlit kitchen. The morning light pours in through the window, and there might be a few people just outside.";

  const corrections = [
    { from: "there is some peoples", to: "there are a few people", reason: "people 本身就是复数；many/some 后用 are，不要再加 -s。" },
    { from: "She is make coffee",    to: "She is making coffee",    reason: "进行时是 be + 动词 -ing。be 后面动词要加 ing。" },
    { from: "The kitchen have",      to: "The kitchen has",         reason: "主语是单数 kitchen，第三人称单数现在时用 has。" },
    { from: "many sunlight",         to: "a lot of sunlight",       reason: "sunlight 不可数，不用 many；a lot of 通用更地道。" },
  ];

  const missed   = ["striped apron", "window above the sink", "morning light"];
  const vocab    = ["pour in", "sunlit", "stream in", "apron"];

  return (
    <div className="su-screen">
      <NavBar title="AI 反馈" />

      <div className="su-body" style={{ paddingBottom: 24 }}>
        {/* thumb */}
        <div style={{ display: "flex", gap: 14, alignItems: "center", marginBottom: 18 }}>
          <div style={{
            width: 64, height: 64, borderRadius: 12,
            background: "repeating-linear-gradient(135deg, oklch(0.93 0.013 70) 0 6px, oklch(0.96 0.008 70) 6px 12px)",
            flex: "0 0 auto",
          }} />
          <div>
            <div className="eyebrow">scene</div>
            <div style={{ fontFamily: "var(--ff-mono)", fontSize: 13, color: "var(--ink)", marginTop: 2 }}>kitchen · morning</div>
            <div style={{ fontFamily: "var(--ff-cn)", fontSize: 11, color: "var(--ink-3)", marginTop: 2 }}>刚刚 · 第 1 次</div>
          </div>
        </div>

        {/* AI sees */}
        <section className="su-card" style={{ marginBottom: 12 }}>
          <div className="card-eyebrow">
            <span className="eyebrow">AI sees in the image</span>
          </div>
          <div className="en">{aiSees}</div>
        </section>

        {/* You said */}
        <section className="su-card" style={{ marginBottom: 12, background: "var(--bg-mute)" }}>
          <div className="card-eyebrow">
            <span className="eyebrow">你说的</span>
          </div>
          <div className="en" style={{ color: "var(--ink-2)" }}>{userSaid}</div>
        </section>

        {/* More native */}
        <section className="su-card" style={{ marginBottom: 18, borderColor: "var(--accent)", borderWidth: 1.5 }}>
          <div className="card-eyebrow">
            <span className="eyebrow" style={{ color: "var(--accent)" }}>more native</span>
            <span className="chip accent">改写</span>
          </div>
          <div className="en">{native}</div>
        </section>

        {/* Corrections */}
        <h3 style={{
          fontFamily: "var(--ff-cn)", fontSize: 13, fontWeight: 600, color: "var(--ink)",
          margin: "8px 0 4px", letterSpacing: 0,
        }}>
          逐点纠正 <span style={{ color: "var(--ink-3)", fontWeight: 400 }}>· {corrections.length} 处</span>
        </h3>
        <div style={{ marginBottom: 18 }}>
          {corrections.map((c, i) => (
            <div key={i} className="su-corr">
              <div className="from">{c.from}</div>
              <div className="arrow">→</div>
              <div className="to">{c.to}</div>
              <div className="reason">{c.reason}</div>
            </div>
          ))}
        </div>

        {/* Missed elements */}
        <h3 style={{
          fontFamily: "var(--ff-cn)", fontSize: 13, fontWeight: 600, color: "var(--ink)",
          margin: "8px 0 8px", letterSpacing: 0,
        }}>
          你漏掉的画面元素
        </h3>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 18 }}>
          {missed.map((m, i) => <span key={i} className="chip">{m}</span>)}
        </div>

        {/* Vocab */}
        <h3 style={{
          fontFamily: "var(--ff-cn)", fontSize: 13, fontWeight: 600, color: "var(--ink)",
          margin: "8px 0 8px", letterSpacing: 0,
        }}>
          建议词汇
        </h3>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 20 }}>
          {vocab.map((v, i) => <span key={i} className="chip accent">{v}</span>)}
        </div>

        {/* Tip */}
        <div style={{
          padding: 14, borderRadius: 10, background: "var(--bg-mute)",
          border: "1px solid var(--rule)", marginBottom: 24,
        }}>
          <div className="eyebrow" style={{ marginBottom: 6 }}>学习建议</div>
          <p style={{
            fontFamily: "var(--ff-cn)", fontSize: 13, color: "var(--ink-2)",
            margin: 0, lineHeight: 1.6, letterSpacing: 0,
          }}>
            你这次主要卡在「主谓一致」上（people / kitchen 两处）。
            下面看到人物 / 物体时，先想"它是单数还是复数"，再选 is/are、has/have。
          </p>
        </div>

        {/* Actions */}
        <div style={{ display: "flex", gap: 8 }}>
          <button className="su-btn su-btn-secondary" style={{ flex: 1, height: 48 }}>
            <Icon name="refresh" size={16} />&nbsp;重说
          </button>
          <button className="su-btn su-btn-secondary" style={{ flex: 1, height: 48 }}>
            下一张 &nbsp;<Icon name="next" size={16} />
          </button>
        </div>
        <button
          className={"su-btn " + (saved ? "su-btn-tertiary" : "su-btn-primary")}
          style={{ marginTop: 10, height: 52, opacity: saved ? 0.65 : 1 }}
          disabled={saved}
        >
          {saved
            ? <><Icon name="check" size={18} />&nbsp;已保存到错题本</>
            : <><Icon name="save" size={18} />&nbsp;保存到错题本</>}
        </button>
      </div>
    </div>
  );
}

Object.assign(window, { LoginScreen, PracticeScreen, FeedbackScreen });
