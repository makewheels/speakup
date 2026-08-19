// SpeakUp · screens-more.jsx
// 4.4 Mistake book · 4.5 Re-practice · 4.6 Inference · 4.7 Profile

// ─────────────────────────────────────────────────────────────
// 4.4 MISTAKE BOOK
// ─────────────────────────────────────────────────────────────
function MistakesScreen({ empty = false, filter = "all" /* all | due | mastered */ }) {
  const items = [
    { from: "there is some peoples", to: "there are a few people", reason: "people 本身复数",     date: "今天",       n: 0, status: "due", scene: "kitchen" },
    { from: "She is make coffee",    to: "She is making coffee",    reason: "be + V-ing",         date: "今天",       n: 0, status: "due", scene: "kitchen" },
    { from: "more cheap",            to: "cheaper",                 reason: "单音节加 -er",       date: "2 天前",     n: 1, status: "due", scene: "market" },
    { from: "I very like dogs",      to: "I really like dogs",      reason: "very 不修饰动词",    date: "3 天前",     n: 2, status: "review", scene: "park" },
    { from: "he don't know",         to: "he doesn't know",         reason: "三单否定 doesn't",   date: "5 天前",     n: 3, status: "review", scene: "office" },
    { from: "open the light",        to: "turn on the light",       reason: "搭配 turn on",       date: "1 周前",     n: 4, status: "mastered", scene: "bedroom" },
    { from: "in last weekend",       to: "last weekend",            reason: "last 前不加 in",     date: "1 周前",     n: 5, status: "mastered", scene: "park" },
  ];

  const shown = filter === "all" ? items
              : filter === "due" ? items.filter(i => i.status !== "mastered")
              : items.filter(i => i.status === "mastered");

  const dueCount = items.filter(i => i.status === "due").length;

  return (
    <div className="su-screen">
      <NavBar title="错题本" right={<Icon name="more" size={20} color="var(--ink-2)" />} />

      <div className="su-body">
        {!empty && (
          <>
            {/* summary */}
            <div className="su-summary">
              <div className="row">
                <div>
                  <div style={{ fontFamily: "var(--ff-mono)", fontSize: 10, letterSpacing: "0.14em", textTransform: "uppercase", color: "oklch(0.78 0.005 60)" }}>
                    in total
                  </div>
                  <div className="big" style={{ marginTop: 6 }}>{items.length}<span style={{ fontSize: 14, marginLeft: 6, fontFamily: "var(--ff-cn)", color: "oklch(0.78 0.005 60)" }}>条</span></div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontFamily: "var(--ff-mono)", fontSize: 10, letterSpacing: "0.14em", textTransform: "uppercase", color: "oklch(0.78 0.005 60)" }}>
                    due today
                  </div>
                  <div className="big" style={{ marginTop: 6 }}>{dueCount}<span style={{ fontSize: 14, marginLeft: 6, fontFamily: "var(--ff-cn)", color: "oklch(0.78 0.005 60)" }}>条</span></div>
                </div>
              </div>
              {dueCount > 0 && (
                <button style={{
                  marginTop: 16, width: "100%", height: 44, borderRadius: 10,
                  border: "1px solid oklch(0.45 0.01 60)",
                  background: "transparent", color: "var(--bg)",
                  fontFamily: "var(--ff-cn)", fontSize: 14, letterSpacing: 0.4, cursor: "pointer",
                }}>
                  开始今天的复习 →
                </button>
              )}
            </div>

            {/* filter tabs */}
            <div style={{ display: "flex", gap: 18, borderBottom: "1px solid var(--rule)", marginBottom: 4 }}>
              {[["all","全部"], ["due","待复习"], ["mastered","已掌握"]].map(([k, l]) => (
                <div key={k} style={{
                  paddingBottom: 10, paddingTop: 4,
                  fontFamily: "var(--ff-cn)", fontSize: 13,
                  color: filter === k ? "var(--ink)" : "var(--ink-3)",
                  fontWeight: filter === k ? 600 : 400,
                  borderBottom: filter === k ? "1.5px solid var(--ink)" : "1.5px solid transparent",
                  marginBottom: -1, cursor: "pointer", letterSpacing: 0.4,
                }}>
                  {l} <span style={{ color: "var(--ink-4)", fontSize: 11, marginLeft: 2 }}>
                    {k === "all" ? items.length : k === "due" ? items.filter(i => i.status !== "mastered").length : items.filter(i => i.status === "mastered").length}
                  </span>
                </div>
              ))}
            </div>

            {/* list */}
            <div>
              {shown.map((m, i) => (
                <div key={i} className="mistake-row">
                  <div className="thumb"></div>
                  <div className="body">
                    <div className="corr-inline">
                      <span className="strike">{m.from}</span>
                      <span className="arrow">→</span>
                      <span className="to">{m.to}</span>
                    </div>
                    <div className="meta">
                      <span>{m.reason}</span>
                    </div>
                    <div className="meta" style={{ marginTop: 4 }}>
                      <span style={{ fontFamily: "var(--ff-mono)", fontSize: 10, letterSpacing: "0.05em", textTransform: "uppercase", color: "var(--ink-3)" }}>
                        {m.scene}
                      </span>
                      <span className="dot"></span>
                      <span>{m.date}</span>
                      <span className="dot"></span>
                      <span>复习 × {m.n}</span>
                    </div>
                  </div>
                  <div className={"tag " + (m.status === "due" ? "due" : m.status === "mastered" ? "mastered" : "")}>
                    {m.status === "due" ? "待复习" : m.status === "mastered" ? "已掌握" : "复习中"}
                  </div>
                </div>
              ))}
            </div>

            <p style={{
              fontFamily: "var(--ff-mono)", fontSize: 10, letterSpacing: "0.1em", textTransform: "uppercase",
              color: "var(--ink-4)", textAlign: "center", margin: "24px 0",
            }}>
              · end of list ·
            </p>
          </>
        )}

        {empty && (
          <div style={{
            display: "flex", flexDirection: "column", alignItems: "center",
            justifyContent: "center", height: "60%", textAlign: "center",
            padding: "40px 20px",
          }}>
            <div style={{
              width: 72, height: 72, borderRadius: 18,
              border: "1px dashed var(--ink-4)",
              display: "flex", alignItems: "center", justifyContent: "center",
              marginBottom: 18,
            }}>
              <Icon name="book" size={28} color="var(--ink-3)" stroke={1.4} />
            </div>
            <p className="serif" style={{ fontSize: 20, color: "var(--ink)", margin: 0 }}>还没有错题</p>
            <p style={{
              fontFamily: "var(--ff-cn)", fontSize: 13, color: "var(--ink-3)",
              margin: "8px 0 24px", letterSpacing: 0,
            }}>去练习里说一段试试</p>
            <button className="su-btn su-btn-primary" style={{ width: 160 }}>去练习</button>
          </div>
        )}
      </div>

      <TabBar active="mistakes" dueCount={dueCount} />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// 4.5 RE-PRACTICE (原图重练)
// ─────────────────────────────────────────────────────────────
function ReviewScreen({ expanded = false, withFeedback = false }) {
  return (
    <div className="su-screen">
      <NavBar
        back
        title="原图重练"
        sub="review · 1 / 3"
      />

      <div className="su-body" style={{ paddingBottom: 24 }}>
        {/* previous mistake — collapsible */}
        <div style={{
          border: "1px solid var(--rule)", borderRadius: 12,
          marginBottom: 16, overflow: "hidden", background: "var(--bg-mute)",
        }}>
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: "12px 14px", cursor: "pointer",
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Icon name="warn" size={16} color="var(--warn)" stroke={1.6} />
              <span style={{ fontFamily: "var(--ff-cn)", fontSize: 13, color: "var(--ink)", fontWeight: 500 }}>
                上次你这样说
              </span>
              <span style={{ fontFamily: "var(--ff-mono)", fontSize: 10, color: "var(--ink-3)", letterSpacing: "0.05em" }}>
                · 3 天前
              </span>
            </div>
            <Icon name={expanded ? "up" : "down"} size={16} color="var(--ink-3)" />
          </div>
          {expanded && (
            <div style={{ padding: "0 14px 14px", borderTop: "1px solid var(--rule)" }}>
              <div style={{ marginTop: 12 }} className="su-corr">
                <div className="from">there is some peoples in the kitchen</div>
                <div className="arrow">→</div>
                <div className="to">there are a few people in the kitchen</div>
                <div className="reason">people 本身就是复数；many/some 后用 are，不要再加 -s。</div>
              </div>
            </div>
          )}
          {!expanded && (
            <div style={{
              padding: "0 14px 12px", fontFamily: "var(--ff-cn)", fontSize: 11,
              color: "var(--ink-3)", letterSpacing: 0,
            }}>
              展开看上次的错处。我们建议你先自己再说一遍。
            </div>
          )}
        </div>

        <ImagePh caption="kitchen · morning" />

        <p style={{
          fontFamily: "var(--ff-cn)", fontSize: 13, color: "var(--ink-2)",
          textAlign: "center", margin: "18px 0 14px", letterSpacing: 0,
        }}>
          {withFeedback ? "AI 反馈如下" : "再说一遍，看看是否还会犯同样的错"}
        </p>

        {!withFeedback && (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", padding: "12px 0 30px" }}>
            <button className="su-rec">
              <Icon name="mic" size={32} color="#fff" />
            </button>
            <div className="su-rec-label">点击开始</div>
          </div>
        )}

        {withFeedback && (
          <>
            {/* progress vs last time */}
            <div style={{
              display: "flex", alignItems: "center", gap: 10,
              padding: "12px 14px", borderRadius: 10,
              background: "var(--ok-soft)", marginBottom: 16,
              border: "1px solid oklch(0.85 0.04 155)",
            }}>
              <Icon name="check" size={18} color="var(--ok)" stroke={2} />
              <div style={{ flex: 1 }}>
                <div style={{ fontFamily: "var(--ff-cn)", fontSize: 13, color: "var(--ok)", fontWeight: 600 }}>
                  克服了一个错题
                </div>
                <div style={{ fontFamily: "var(--ff-cn)", fontSize: 11, color: "var(--ink-2)", marginTop: 2, letterSpacing: 0 }}>
                  「主谓一致」这次说对了。下次复习时间已延后。
                </div>
              </div>
            </div>

            {/* mini feedback */}
            <section className="su-card" style={{ marginBottom: 12 }}>
              <div className="card-eyebrow">
                <span className="eyebrow">你这次说</span>
              </div>
              <div className="en">There are a few people in the kitchen. A woman is making coffee.</div>
            </section>

            <section className="su-card" style={{ marginBottom: 18, borderColor: "var(--accent)" }}>
              <div className="card-eyebrow">
                <span className="eyebrow" style={{ color: "var(--accent)" }}>more native</span>
              </div>
              <div className="en">A woman is brewing coffee in a kitchen with a few people around.</div>
            </section>

            <div style={{ display: "flex", gap: 10 }}>
              <button className="su-btn su-btn-secondary" style={{ flex: 1, height: 48 }}>下一题</button>
              <button className="su-btn su-btn-primary" style={{ flex: 1, height: 48 }}>
                <Icon name="spark" size={16} />&nbsp;举一反三
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// 4.6 INFERENCE (举一反三) — V1.1 concept
// ─────────────────────────────────────────────────────────────
function InferenceScreen() {
  return (
    <div className="su-screen">
      <NavBar back title="举一反三" sub="grammar · subject-verb agreement" />

      <div className="su-body" style={{ paddingBottom: 24 }}>
        {/* concept band */}
        <div style={{
          padding: "14px 16px", borderRadius: 12,
          background: "var(--accent-soft)",
          border: "1px solid oklch(0.86 0.04 245)",
          marginBottom: 18,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
            <span className="ai-tag"><Icon name="spark" size={10} stroke={2} />&nbsp;ai 生成新场景</span>
          </div>
          <p style={{ fontFamily: "var(--ff-cn)", fontSize: 13, color: "var(--ink)", margin: 0, lineHeight: 1.55, letterSpacing: 0 }}>
            你之前在 <span style={{ fontFamily: "var(--ff-mono)", color: "var(--warn)" }}>"there is some peoples"</span> 上出错。
            换一张图，看你还会不会犯。
          </p>
        </div>

        <ImagePh caption="market · afternoon · NEW" />

        {/* mini meta — how AI picked it */}
        <div style={{
          display: "flex", alignItems: "center", gap: 8,
          margin: "12px 0 0", flexWrap: "wrap",
        }}>
          <span className="chip">考点 · subject-verb agreement</span>
          <span className="chip">已答对 1 / 3</span>
        </div>

        <p style={{
          fontFamily: "var(--ff-cn)", fontSize: 13, color: "var(--ink-2)",
          textAlign: "center", margin: "22px 0 14px", letterSpacing: 0,
        }}>
          看着这张新图，用英语描述
        </p>

        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", padding: "0 0 24px" }}>
          <button className="su-rec">
            <Icon name="mic" size={32} color="#fff" />
          </button>
          <div className="su-rec-label">点击开始</div>
        </div>

        <hr className="hr" />

        <p style={{
          fontFamily: "var(--ff-mono)", fontSize: 10, color: "var(--ink-3)",
          letterSpacing: "0.1em", textTransform: "uppercase", margin: "0 0 8px",
        }}>
          coming next · v1.1
        </p>
        <p style={{
          fontFamily: "var(--ff-cn)", fontSize: 12, color: "var(--ink-3)", margin: 0,
          lineHeight: 1.55, letterSpacing: 0,
        }}>
          说完后，AI 会专门检查这次"主谓一致"有没有再错。
          答对一次，下次的间隔翻倍。
        </p>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// 4.7 PROFILE
// ─────────────────────────────────────────────────────────────
function ProfileScreen() {
  const bars = [3, 6, 2, 5, 8, 4, 7];
  const max = Math.max(...bars);
  const days = ["一", "二", "三", "四", "五", "六", "日"];

  return (
    <div className="su-screen">
      <NavBar title="我的" />

      <div className="su-body" style={{ paddingBottom: 24 }}>
        {/* profile row */}
        <div style={{ display: "flex", gap: 14, alignItems: "center", padding: "8px 0 20px" }}>
          <div style={{
            width: 56, height: 56, borderRadius: 28,
            background: "var(--ink)", color: "var(--bg)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontFamily: "var(--ff-serif)", fontSize: 24, letterSpacing: "-0.02em",
          }}>
            用
          </div>
          <div>
            <div style={{ fontFamily: "var(--ff-cn)", fontSize: 17, color: "var(--ink)", fontWeight: 500 }}>用户1234</div>
            <div style={{ fontFamily: "var(--ff-mono)", fontSize: 12, color: "var(--ink-3)", marginTop: 2, letterSpacing: "0.04em" }}>
              138 **** 0000
            </div>
          </div>
        </div>

        {/* stats grid */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 12 }}>
          <div className="stat-tile">
            <div className="n">7</div>
            <div className="l">连续打卡 / 天</div>
          </div>
          <div className="stat-tile">
            <div className="n">42</div>
            <div className="l">总练习 / 次</div>
          </div>
          <div className="stat-tile">
            <div className="n">18</div>
            <div className="l">错题 / 个</div>
          </div>
          <div className="stat-tile">
            <div className="n">6</div>
            <div className="l">已掌握 / 个</div>
          </div>
        </div>

        {/* weekly chart */}
        <section className="su-card" style={{ marginBottom: 18 }}>
          <div className="card-eyebrow">
            <span className="eyebrow">this week</span>
            <span style={{ fontFamily: "var(--ff-cn)", fontSize: 11, color: "var(--ink-3)" }}>本周练习</span>
          </div>
          <div style={{
            display: "grid", gridTemplateColumns: "repeat(7, 1fr)",
            gap: 6, alignItems: "end", height: 88, marginTop: 8,
          }}>
            {bars.map((v, i) => (
              <div key={i} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
                <div style={{ display: "flex", alignItems: "end", height: 70, width: "100%" }}>
                  <div style={{
                    width: "100%", borderRadius: 4,
                    height: `${(v / max) * 100}%`,
                    background: i === bars.length - 1 ? "var(--ink)" : "var(--ink-4)",
                  }} />
                </div>
                <div style={{ fontFamily: "var(--ff-cn)", fontSize: 10, color: "var(--ink-3)" }}>{days[i]}</div>
              </div>
            ))}
          </div>
        </section>

        {/* settings rows */}
        <div className="su-card" style={{ padding: 0 }}>
          {[
            ["练习提醒", "每天 20:00"],
            ["语音识别", "Chrome 浏览器"],
            ["反馈邮箱", "hi@speakup.app"],
            ["版本", "v0.1.0 · MVP"],
          ].map(([k, v], i, a) => (
            <div key={i} style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              padding: "14px 16px", borderBottom: i < a.length - 1 ? "1px solid var(--rule)" : "0",
              fontFamily: "var(--ff-cn)", fontSize: 14,
            }}>
              <span style={{ color: "var(--ink)" }}>{k}</span>
              <span style={{ color: "var(--ink-3)", fontFamily: "var(--ff-mono)", fontSize: 12, letterSpacing: 0.02 }}>{v}</span>
            </div>
          ))}
        </div>

        <button className="su-btn su-btn-secondary" style={{ marginTop: 18, height: 48, color: "var(--warn)" }}>
          退出登录
        </button>
      </div>

      <TabBar active="me" dueCount={3} />
    </div>
  );
}

Object.assign(window, { MistakesScreen, ReviewScreen, InferenceScreen, ProfileScreen });
