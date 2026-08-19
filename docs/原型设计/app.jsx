// SpeakUp · app.jsx — design canvas composition

const { useState: useStateApp, useEffect: useEffectApp, useRef: useRefApp } = React;

// helper: wrap a screen with the iOS device frame
function P({ children }) {
  return <IOSDevice width={375} height={812} dark={false}>{children}</IOSDevice>;
}

// ───── Interactive practice prototype (single artboard, live state) ─────
function InteractivePractice() {
  const [state, setState] = useStateApp("ready");       // loading | ready | recording | review | evaluating
  const [transcript, setTranscript] = useStateApp("");
  const [elapsed, setElapsed]   = useStateApp("0:00");
  const [seconds, setSeconds]   = useStateApp(0);
  const [showFeedback, setShowFeedback] = useStateApp(false);
  const [saved, setSaved] = useStateApp(false);
  const timerRef = useRefApp(null);

  // fake transcript stream
  const fakeWords = "There is a woman. She is make coffee in the kitchen. The kitchen have many sunlight and there is some peoples outside maybe.".split(" ");
  const wordIxRef = useRefApp(0);

  useEffectApp(() => {
    if (state === "recording") {
      wordIxRef.current = 0;
      setTranscript("");
      setSeconds(0);
      timerRef.current = setInterval(() => {
        setSeconds(s => {
          const n = s + 1;
          const mm = Math.floor(n / 60);
          const ss = (n % 60).toString().padStart(2, "0");
          setElapsed(`${mm}:${ss}`);
          return n;
        });
        // stream new word every ~600ms
        if (wordIxRef.current < fakeWords.length) {
          setTranscript(t => t + (t ? " " : "") + fakeWords[wordIxRef.current]);
          wordIxRef.current += 1;
        }
      }, 600);
    } else {
      clearInterval(timerRef.current);
    }
    return () => clearInterval(timerRef.current);
  }, [state]);

  function start() {
    setShowFeedback(false);
    setSaved(false);
    setState("recording");
  }
  function stop()  { setState("review"); }
  function reset() { setTranscript(""); setElapsed("0:00"); setSeconds(0); setState("ready"); }
  function evaluate() {
    setState("evaluating");
    setTimeout(() => { setShowFeedback(true); setState("ready"); }, 1600);
  }

  if (showFeedback) {
    return (
      <div className="su-screen">
        <header className="su-nav">
          <div className="su-nav-side" onClick={() => { setShowFeedback(false); reset(); }} style={{ cursor: "pointer" }}>
            <Icon name="back" size={22} />
          </div>
          <div style={{ textAlign: "center" }}><h1>AI 反馈</h1></div>
          <div className="su-nav-side right"></div>
        </header>
        <div className="su-body" style={{ paddingBottom: 24 }}>
          <section className="su-card" style={{ marginBottom: 12 }}>
            <div className="card-eyebrow"><span className="eyebrow">AI sees in the image</span></div>
            <div className="en">A bright kitchen in the morning. A young woman in a striped apron is making coffee, sunlight streaming in through the window.</div>
          </section>
          <section className="su-card" style={{ marginBottom: 12, background: "var(--bg-mute)" }}>
            <div className="card-eyebrow"><span className="eyebrow">你说的</span></div>
            <div className="en" style={{ color: "var(--ink-2)" }}>{transcript || "(请先录音)"}</div>
          </section>
          <section className="su-card" style={{ marginBottom: 18, borderColor: "var(--accent)", borderWidth: 1.5 }}>
            <div className="card-eyebrow">
              <span className="eyebrow" style={{ color: "var(--accent)" }}>more native</span>
              <span className="chip accent">改写</span>
            </div>
            <div className="en">A woman is making coffee in a sunlit kitchen, with morning light pouring in and a few people just outside.</div>
          </section>
          <h3 style={{ fontFamily: "var(--ff-cn)", fontSize: 13, fontWeight: 600, margin: "8px 0 4px" }}>逐点纠正 · 4 处</h3>
          {[
            ["there is some peoples", "there are a few people", "people 本身复数；many/some 后用 are"],
            ["She is make coffee",    "She is making coffee",    "进行时是 be + V-ing"],
            ["The kitchen have",      "The kitchen has",         "kitchen 单数 → has"],
            ["many sunlight",         "a lot of sunlight",       "sunlight 不可数 → 不用 many"],
          ].map(([f, t, r], i) => (
            <div key={i} className="su-corr">
              <div className="from">{f}</div>
              <div className="arrow">→</div>
              <div className="to">{t}</div>
              <div className="reason">{r}</div>
            </div>
          ))}
          <div style={{ display: "flex", gap: 8, marginTop: 20 }}>
            <button className="su-btn su-btn-secondary" style={{ flex: 1, height: 48 }} onClick={() => { setShowFeedback(false); reset(); }}>
              <Icon name="refresh" size={16} />&nbsp;重说
            </button>
            <button className="su-btn su-btn-secondary" style={{ flex: 1, height: 48 }} onClick={() => { setShowFeedback(false); reset(); }}>
              下一张 &nbsp;<Icon name="next" size={16} />
            </button>
          </div>
          <button
            className={"su-btn " + (saved ? "su-btn-tertiary" : "su-btn-primary")}
            style={{ marginTop: 10, height: 52, opacity: saved ? 0.65 : 1 }}
            disabled={saved}
            onClick={() => setSaved(true)}
          >
            {saved ? <><Icon name="check" size={18} />&nbsp;已保存到错题本</> : <><Icon name="save" size={18} />&nbsp;保存到错题本</>}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="su-screen">
      <NavBar title="" right={<span style={{ fontFamily: "var(--ff-mono)", fontSize: 11, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--ink-3)" }}>scene · 1</span>} />
      <div className="su-body">
        <ImagePh caption="kitchen · morning" loading={state === "loading"} />
        <p style={{
          fontFamily: "var(--ff-cn)", fontSize: 13, color: "var(--ink-2)",
          textAlign: "center", margin: "18px 0 14px", letterSpacing: 0,
        }}>
          {state === "ready" ? "看着图，用英语描述"
            : state === "recording" ? "正在听…"
            : state === "review" ? "看一眼，要不要让 AI 看？"
            : "AI 正在看你的描述…"}
        </p>
        {(state === "recording" || state === "review" || state === "evaluating") && (
          <div className={"su-transcript" + (!transcript ? " empty" : "")}>
            {transcript || "（说话内容会显示在这里）"}
            {state === "recording" && <span className="live-dot"></span>}
          </div>
        )}
        {state === "recording" && (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, marginTop: 14 }}>
            <span className="mono" style={{ fontSize: 13, color: "var(--warn)" }}>● REC</span>
            <span className="mono" style={{ fontSize: 13, color: "var(--ink-2)" }}>{elapsed}</span>
          </div>
        )}
        <div style={{ height: state === "review" || state === "evaluating" ? 18 : 30 }}></div>

        {state === "ready" && (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
            <button className="su-rec" onClick={start}><Icon name="mic" size={32} color="#fff" /></button>
            <div className="su-rec-label">点击开始</div>
          </div>
        )}
        {state === "recording" && (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
            <button className="su-rec recording" onClick={stop}><Icon name="stop" size={28} color="#fff" /></button>
            <div className="su-rec-label">点击停止</div>
          </div>
        )}
        {state === "review" && (
          <div style={{ display: "flex", gap: 10 }}>
            <button className="su-btn su-btn-secondary" style={{ flex: 1 }} onClick={reset}>
              <Icon name="refresh" size={16} />&nbsp;重说
            </button>
            <button className="su-btn su-btn-primary" style={{ flex: 2 }} onClick={evaluate} disabled={!transcript}>
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
      <TabBar active="practice" dueCount={3} />
    </div>
  );
}

// ───── App: design canvas with all screens ─────
function App() {
  return (
    <DesignCanvas>
      {/* Cover / intro */}
      <DCSection id="overview" title="SpeakUp — 看图说英语" subtitle="按 docs/design/spec.md · v0.1 demo 设计 · 移动端 375 × 812">
        <DCArtboard id="intro" label="设计说明" width={520} height={812}>
          <div style={{
            padding: "56px 44px", height: "100%", boxSizing: "border-box",
            fontFamily: "var(--ff-sans), var(--ff-cn)", background: "var(--bg)", color: "var(--ink)",
            display: "flex", flexDirection: "column",
          }}>
            <div className="eyebrow">DESIGN BRIEF</div>
            <h1 className="serif" style={{ fontSize: 56, fontWeight: 400, lineHeight: 1, margin: "16px 0 24px", letterSpacing: "-0.025em" }}>
              SpeakUp
            </h1>
            <p style={{ fontFamily: "var(--ff-cn)", fontSize: 15, lineHeight: 1.7, color: "var(--ink-2)", margin: 0, letterSpacing: 0 }}>
              看图片 → 用英语描述 → AI 客观纠正不地道的表达 → 沉淀错题本 → 间隔复习。
            </p>
            <hr className="hr" style={{ margin: "28px 0" }} />
            <div className="eyebrow" style={{ marginBottom: 10 }}>气质</div>
            <p style={{ fontFamily: "var(--ff-cn)", fontSize: 14, lineHeight: 1.75, color: "var(--ink-2)", margin: 0, letterSpacing: 0 }}>
              客观 · 克制 · 私人感 · 不哄 · 不打鸡血。<br/>
              像一个不评判你的私人老师。
            </p>
            <hr className="hr" style={{ margin: "28px 0" }} />
            <div className="eyebrow" style={{ marginBottom: 10 }}>视觉系统</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, fontSize: 12, fontFamily: "var(--ff-cn)" }}>
              <div>
                <div style={{ color: "var(--ink-3)", marginBottom: 6, fontFamily: "var(--ff-mono)", textTransform: "uppercase", letterSpacing: "0.1em", fontSize: 10 }}>type</div>
                <div className="serif" style={{ fontSize: 22, lineHeight: 1 }}>Newsreader</div>
                <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 2 }}>serif · 标题 / AI 英文</div>
                <div style={{ marginTop: 12, fontFamily: "var(--ff-sans)", fontSize: 16, fontWeight: 500 }}>Geist</div>
                <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 2 }}>sans · UI</div>
                <div style={{ marginTop: 12, fontFamily: "var(--ff-mono)", fontSize: 14 }}>JetBrains Mono</div>
                <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 2 }}>mono · 引述 / 纠正</div>
              </div>
              <div>
                <div style={{ color: "var(--ink-3)", marginBottom: 6, fontFamily: "var(--ff-mono)", textTransform: "uppercase", letterSpacing: "0.1em", fontSize: 10 }}>color</div>
                {[
                  ["bg", "var(--bg)", "warm paper"],
                  ["ink", "var(--ink)", "primary text"],
                  ["accent", "var(--accent)", "ink-blue · AI"],
                  ["warn", "var(--warn)", "用户错处"],
                  ["ok", "var(--ok)", "已掌握"],
                ].map(([k, v, n]) => (
                  <div key={k} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                    <div style={{ width: 22, height: 22, borderRadius: 5, background: v, border: "1px solid var(--rule)" }} />
                    <div style={{ flex: 1, fontFamily: "var(--ff-mono)", fontSize: 11, color: "var(--ink)" }}>{k}</div>
                    <div style={{ fontSize: 10, color: "var(--ink-3)" }}>{n}</div>
                  </div>
                ))}
              </div>
            </div>
            <hr className="hr" style={{ margin: "28px 0" }} />
            <div className="eyebrow" style={{ marginBottom: 10 }}>页面顺序</div>
            <ol style={{
              fontFamily: "var(--ff-cn)", fontSize: 13, color: "var(--ink-2)",
              paddingLeft: 18, margin: 0, lineHeight: 1.8, letterSpacing: 0,
            }}>
              <li>4.1 登录</li>
              <li>4.2 练习主页（4 种状态）</li>
              <li>4.3 AI 反馈页</li>
              <li>4.4 错题本</li>
              <li>4.5 原图重练</li>
              <li>4.6 举一反三（V1.1 概念）</li>
              <li>4.7 个人中心</li>
            </ol>
            <div style={{ flex: 1 }} />
            <div style={{ fontFamily: "var(--ff-mono)", fontSize: 10, color: "var(--ink-4)", letterSpacing: "0.1em", textTransform: "uppercase", marginTop: 24 }}>
              · 点击下方任意画板进入全屏查看 ·
            </div>
          </div>
        </DCArtboard>

        <DCArtboard id="interactive" label="🟢 可交互原型 · 点录音试一下" width={375} height={812}>
          <P><InteractivePractice /></P>
        </DCArtboard>
      </DCSection>

      {/* 4.1 Login */}
      <DCSection id="login" title="4.1 登录" subtitle="手机号直接登录（MVP）· 4 个状态">
        <DCArtboard id="login-empty"     label="A · 空白态"        width={375} height={812}><P><LoginScreen state="empty" /></P></DCArtboard>
        <DCArtboard id="login-typing"    label="B · 输入中"        width={375} height={812}><P><LoginScreen state="typing" phone="13800001234" /></P></DCArtboard>
        <DCArtboard id="login-submit"    label="C · 提交中"        width={375} height={812}><P><LoginScreen state="submitting" phone="13800001234" /></P></DCArtboard>
        <DCArtboard id="login-error"     label="D · 格式错误"      width={375} height={812}><P><LoginScreen state="error" phone="12345" /></P></DCArtboard>
      </DCSection>

      {/* 4.2 Practice */}
      <DCSection id="practice" title="4.2 练习主页" subtitle="核心页面 · 5 个连续状态">
        <DCArtboard id="prac-loading"    label="A · 加载图片"       width={375} height={812}><P><PracticeScreen state="loading" /></P></DCArtboard>
        <DCArtboard id="prac-ready"      label="B · 待录音"         width={375} height={812}><P><PracticeScreen state="ready" /></P></DCArtboard>
        <DCArtboard id="prac-rec"        label="C · 录音中"         width={375} height={812}><P><PracticeScreen state="recording" transcript="There is a woman. She is make coffee in the kitchen." elapsed="0:12" /></P></DCArtboard>
        <DCArtboard id="prac-review"     label="D · 录完待提交"     width={375} height={812}><P><PracticeScreen state="review" transcript="There is a woman. She is make coffee in the kitchen. The kitchen have many sunlight and there is some peoples outside maybe." /></P></DCArtboard>
        <DCArtboard id="prac-eval"       label="E · AI 评估中"      width={375} height={812}><P><PracticeScreen state="evaluating" transcript="There is a woman. She is make coffee in the kitchen. The kitchen have many sunlight and there is some peoples outside maybe." /></P></DCArtboard>
      </DCSection>

      {/* 4.3 Feedback */}
      <DCSection id="feedback" title="4.3 AI 反馈" subtitle="纵向滚动卡片流 · 点保存进入错题本">
        <DCArtboard id="fb-unsaved"      label="A · 反馈展开"       width={375} height={1480}><P><FeedbackScreen saved={false} /></P></DCArtboard>
        <DCArtboard id="fb-saved"        label="B · 已保存"         width={375} height={1480}><P><FeedbackScreen saved={true} /></P></DCArtboard>
      </DCSection>

      {/* 4.4 Mistake book */}
      <DCSection id="mistakes" title="4.4 错题本" subtitle="间隔复习驱动 · 列表 + 摘要">
        <DCArtboard id="mb-all"          label="A · 全部"           width={375} height={812}><P><MistakesScreen filter="all" /></P></DCArtboard>
        <DCArtboard id="mb-due"          label="B · 待复习"         width={375} height={812}><P><MistakesScreen filter="due" /></P></DCArtboard>
        <DCArtboard id="mb-mastered"     label="C · 已掌握"         width={375} height={812}><P><MistakesScreen filter="mastered" /></P></DCArtboard>
        <DCArtboard id="mb-empty"        label="D · 空态（新用户）" width={375} height={812}><P><MistakesScreen empty /></P></DCArtboard>
      </DCSection>

      {/* 4.5 Re-practice */}
      <DCSection id="review" title="4.5 原图重练" subtitle="V1.1 · 对照上次错处 + 比较进步">
        <DCArtboard id="rv-collapsed"    label="A · 上次错处收起"   width={375} height={812}><P><ReviewScreen expanded={false} /></P></DCArtboard>
        <DCArtboard id="rv-expanded"     label="B · 上次错处展开"   width={375} height={812}><P><ReviewScreen expanded={true} /></P></DCArtboard>
        <DCArtboard id="rv-done"         label="C · 这次说对了"     width={375} height={812}><P><ReviewScreen expanded={false} withFeedback={true} /></P></DCArtboard>
      </DCSection>

      {/* 4.6 Inference */}
      <DCSection id="inference" title="4.6 举一反三（V1.1 概念）" subtitle="AI 按同考点生成新场景 · 暂用占位图">
        <DCArtboard id="inf-concept"     label="同考点 · 新场景"   width={375} height={812}><P><InferenceScreen /></P></DCArtboard>
      </DCSection>

      {/* 4.7 Profile */}
      <DCSection id="profile" title="4.7 我的" subtitle="MVP 轻量 · 数字 + 退出">
        <DCArtboard id="me"              label="个人中心"           width={375} height={812}><P><ProfileScreen /></P></DCArtboard>
      </DCSection>

    </DesignCanvas>
  );
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);
