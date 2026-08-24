# 发音纠正 · 产品与实施方案

> 状态：首版代码已接入（2026-08-24）；腾讯服务与后付费已开通，独立最小权限身份真实 WSS 请求已通过，生产配置已启用。
> 文档分工：厂商横评与价格/合规细节见 `docs/评测/发音纠正选型调研.md`；**产品形态、数据契约、分工与落地计划以本文为准**；可交互样张见同目录 `pronunciation-card-demo.html`（浏览器直接打开）。
>
> 需求原点（用户原话提炼）：要的不是分数，是**纠正**——"哪个词错误、我的发音是什么、错在哪里、对的什么样；重音一个在首字母，然后对的什么样"。

## 0. 这份文档回答哪些问题

按评审时最常被问的顺序：

1. 用户要什么？（§1）
2. 整体架构长什么样、每一层谁负责什么？（§2）
3. "纠正"这句话到底**谁说出来**的？（§2.3，含常见误解澄清）
4. 引擎返回什么、不返回什么？（§3，含完整字段表与 mock 示例）
5. 腾讯好几种评测模式，选哪种、为什么？（§3.2）
6. 产品上长什么样、怎么交互？（§4，对照 demo）
7. "再练一次"是什么、一个词怎么练？（§4.3）
8. 人工规则库第一版写哪些？（§5）
9. 供应商选谁、怎么定？（§7）
10. 接口、数据模型、成本、隐私、分几期做？（§8–§11）

## 1. 背景与需求

### 1.1 现状缺口

SpeakUp 现有链路：录音 → ASR 转文字 → 文本评估（内容/语法/表达/分数）。这条链路**不保留声学信息**：

- 文本大模型只看到转写，音素/重音/音高/节奏已丢失；
- 普通 ASR 会利用上下文"脑补"纠正不标准发音——识别结果正确 ≠ 发音正确；
- 因此现有产品回答不了"我这个**词**读得对不对"。

### 1.2 验收口径（用户给定）

功能成立 = 对一次练习能给出：

1. **哪个词错了**（最多挑 3 个最值得改的）；
2. **我发成了什么**（IPA，如 `/sriː/`）；
3. **正确的应该是什么**（IPA + 标准音可听）；
4. **错在哪**（哪个音素、重音该在哪个音节 vs 你实际放在哪）；
5. **怎么改**（一句人话教法）+ **马上能练**（单词级反馈闭环）。

### 1.3 非目标

- 不让大模型当评分器（§2.4）；
- 不因本功能新增永久原始音频存储（§9）；
- 首发不做：错题本联动、教练自由点评（音频模型听韵律）——列为后续延伸（§12）。

## 2. 架构与分工

### 2.1 总览

```
用户录音（现有 MediaRecorder，已在 OSS）
  │
  ├─① 评测引擎（尺子）──── 结构化事实：检测音素 vs 参考音素 / 逐音素分 / 重音该不该 vs 实际 / 时间戳
  │
  ├─② 确定性解释器（药方）── 首版按音素差异/重音事实生成短提示；完整规则库见后续（§5）
  │
  ├─④ 官方映射表（显示）── 引擎音素符号 → IPA（查表，非模型生成）
  │
  └─⑤ 自建 TTS（标准音）── 合成目标词/句的标准朗读
前端「发音」卡渲染 ①③④⑤ + 按时间戳裁你的原音回放
```

### 2.2 分工表

| 层 | 输入 | 输出 | 不做什么 |
|---|---|---|---|
| 评测引擎 | 音频 + 参考文本 | 事实（§3 字段表） | 不出人话建议、不出标准音频 |
| 确定性解释器 | 音素对错与重音事实 | 一句短提示 | 不听音频、不改判；首版不额外调用 LLM |
| 映射表 | 引擎音素符号 | IPA 字符串 | ——（纯查表） |
| TTS | 目标词/句 | 标准音音频 | —— |

### 2.3 "谁说出来"——逐句归因（澄清常见误解）

以卡片文案「把 th 发成了「s」的嘶音。舌尖轻抵上齿、气流从舌齿缝出，别用「思」开头。」为例：

| 片段 | 来源 |
|---|---|
| "th 发成了 s"（**哪里错**） | 引擎事实：`Phone=s` vs `ReferencePhone=th` |
| "舌尖轻抵上齿…"（**怎么改**） | 规则库中 th→s 条目的人工教法 |
| 整句的自然语言组织 | 首版确定性模板；不增加一次模型调用 |
| `/sriː/` vs `/θriː/` 显示 | 腾讯模式 4 的 `F_IPA=true` 返回 |
| 标准音 | 自建 TTS |
| "你的原音 0:09.2" | 引擎时间戳裁现有录音 |

**常见误解澄清**：

- 误解 A："引擎会返回纠正建议文字" → 不会。官方文档明确：只返回评分与音素对比等结构化数据，不返回自然语言建议。
- 误解 B："把引擎结果再喂给大模型让它判断哪里错" → 方向反了。首版连文案都用确定性模板；"哪里错"只由引擎事实决定。
- 误解 C："IPA 是模型翻译的" → 不是，腾讯通过 `F_IPA=true` 返回国际音标。

### 2.4 为什么首版不用额外模型解释、更不给模型音频

到文案层，"听"已由引擎完成。首版直接用可测试的模板把音素和重音事实写成短提示；未来只有完整规则库需要更自然的表达时，才考虑加文字模型。再喂音频给音频模型：

1. **重复判断**：它又听一遍自己下结论，可能与引擎事实打架，产品无法展示两个矛盾说法；
2. **幻觉回流**：专门用引擎堵住的"模型编听觉判断"问题重新开门；
3. **贵且慢**：音频 token 成本比文本高一个量级，且不提供新信息。

音频多模态模型（Qwen2.5-Omni/Qwen2-Audio/GPT-4o/Gemini，均"能听"）的合理位置只有两处：候选路线 B（§7，整条链路替代引擎，需实测验证）；后续"教练自由点评"（§12）。

### 2.5 为什么不让 LLM 直接当评分器

- 文本模型看不到声学信息；音频模型能听但**无稳定可校准的逐音素契约**，一致性未验证，会自信地编；
- 专用引擎是确定性契约（同样输入同样字段），可验收、可回归。

## 3. 引擎数据契约（以腾讯 SOE-N 为例）

### 3.1 模式不是"只有长度区别"

| `eval_mode` | 用途 | 参考文本 | 返回重点 |
|---|---|---|---|
| 0 单词 | 跟读一个词 | 有 | 词+音素对比（"再练一次"循环用它） |
| 1 句子 | ≤30 词 | 有 | 逐词分+时间戳 |
| 2 段落 | ≤120 词 | 有 | 逐词分+时间戳 |
| 3 自由说 | 无预设文本 | **无** | 整体流利/清晰+逐词分（"哪个词错"判不准，不作主链路） |
| 4 音素纠错 | 裁出的单词片段二次诊断 | 有（该词） | **检测音素 vs 参考音素、Stress vs DetectedStress、音素时间戳** |
| 5/6 情景 | 候选答案题型 | 有 | 场景匹配（暂不用） |

### 3.2 两段式选择

```
第一遍 · 模式 2（回答 ≤30 词时模式 1）
  参考文本 = ASR 转写（让引擎知道你"想说"什么，才能逐词判对错）
  拿：整体分 + 逐词 PronAccuracy + 逐词时间戳 → 挑 ≤3 低分词
第二遍 · 模式 4
  按时间戳裁低分词片段送检
  拿：Phone vs ReferencePhone + Stress vs DetectedStress + 音素时间戳
```

不用模式 3 做主链路的理由：无参考文本时引擎只能评"说得清不清楚"，不能判"这个词读对没有"。ASR 转写当参考的已知边界：转写错词时参考即错——由"低分词才二次送检 + 展示上限 3 + 用户可忽略"兜底，试点期记录该误报率。

### 3.3 返回字段表（模式 4，官方文档 107390）

词级 `Words[]`：`Word`（识别词）、`ReferenceWord`（参考词）、`PronAccuracy`（词精准度）、`PronFluency`、`MemBeginTime/MemEndTime`（ms）、`PhoneInfos[]`。

音素级 `PhoneInfos[]`：

| 字段 | 含义 | 产品用途 |
|---|---|---|
| `Phone` | **检测音素**（你实际发的） | "你的发音" |
| `ReferencePhone` | **参考音素**（标准） | "正确" |
| `PronAccuracy` | 音素分 | 排序/门槛 |
| `Stress` | 参考音素**应否**重读 | 重音对比·期望 |
| `DetectedStress` | 你**实际**重读否 | 重音对比·实际 |
| `MemBeginTime/EndTime` | 音素时间戳 | 裁原音片段 |
| `ReferenceLetter` | 音素对应字母（开 `F_P2L`） | 展示"哪个字母" |

**引擎不返回**：标准音音频和自然语言建议。IPA 通过模式 4 的 `F_IPA=true` 请求返回；标准音仍走现有 TTS。

### 3.4 完整 mock 示例

5 句话参考文本（约 35 秒）：*I went to the beach last weekend with my friends. The weather was really nice, so we stayed there for three hours. My friend is a sailor and he told us many interesting stories. I think traveling is a very comfortable way to relax. Next time I want to visit a small island and record a video.*

```json
{
  "code": 0, "message": "success", "final": 1, "voice_id": "a1b2…",
  "result": {
    "OverallScore": 71.5, "PronAccuracy": 69.0,
    "PronFluency": 78.5, "PronCompleteness": 100.0,
    "Words": [
      { "Word": "three", "ReferenceWord": "three",
        "PronAccuracy": 42.0, "PronFluency": 2.1,
        "MemBeginTime": 9200, "MemEndTime": 9750,
        "PhoneInfos": [
          { "Phone": "s",  "ReferencePhone": "th", "PronAccuracy": 31.0,
            "Stress": false, "DetectedStress": false,
            "MemBeginTime": 9200, "MemEndTime": 9380, "ReferenceLetter": "t" },
          { "Phone": "r",  "ReferencePhone": "r",  "PronAccuracy": 88.0,
            "Stress": false, "DetectedStress": false,
            "MemBeginTime": 9380, "MemEndTime": 9520, "ReferenceLetter": "h" },
          { "Phone": "iy", "ReferencePhone": "iy", "PronAccuracy": 91.0,
            "Stress": false, "DetectedStress": false,
            "MemBeginTime": 9520, "MemEndTime": 9750, "ReferenceLetter": "ee" }
        ] },
      { "Word": "sailor", "ReferenceWord": "sailor",
        "PronAccuracy": 47.5, "MemBeginTime": 15400, "MemEndTime": 16100,
        "PhoneInfos": [
          { "Phone": "s",  "ReferencePhone": "s",  "PronAccuracy": 93.0,
            "Stress": true,  "DetectedStress": true,
            "MemBeginTime": 15400, "MemEndTime": 15560, "ReferenceLetter": "s" },
          { "Phone": "eh", "ReferencePhone": "ey", "PronAccuracy": 38.0,
            "Stress": true,  "DetectedStress": true,
            "MemBeginTime": 15560, "MemEndTime": 15780, "ReferenceLetter": "a" },
          { "Phone": "l",  "ReferencePhone": "l",  "PronAccuracy": 84.0,
            "Stress": false, "DetectedStress": false,
            "MemBeginTime": 15780, "MemEndTime": 15920, "ReferenceLetter": "l" },
          { "Phone": "er", "ReferencePhone": "er", "PronAccuracy": 81.0,
            "Stress": false, "DetectedStress": false,
            "MemBeginTime": 15920, "MemEndTime": 16100, "ReferenceLetter": "or" }
        ] },
      { "Word": "comfortable", "ReferenceWord": "comfortable",
        "PronAccuracy": 55.0, "MemBeginTime": 24300, "MemEndTime": 25400,
        "PhoneInfos": [
          { "Phone": "k",  "ReferencePhone": "k",  "PronAccuracy": 72.0,
            "Stress": true,  "DetectedStress": false,
            "MemBeginTime": 24300, "MemEndTime": 24450, "ReferenceLetter": "c" },
          { "Phone": "ah", "ReferencePhone": "ah", "PronAccuracy": 51.0,
            "Stress": false, "DetectedStress": true,
            "MemBeginTime": 24450, "MemEndTime": 24700, "ReferenceLetter": "o" },
          { "Phone": "f",  "ReferencePhone": "f",  "PronAccuracy": 86.0,
            "Stress": false, "DetectedStress": false,
            "MemBeginTime": 24700, "MemEndTime": 24850, "ReferenceLetter": "m" }
        ] },
      { "Word": "very", "ReferenceWord": "very",
        "PronAccuracy": 49.0, "MemBeginTime": 22100, "MemEndTime": 22600,
        "PhoneInfos": [
          { "Phone": "w", "ReferencePhone": "v", "PronAccuracy": 35.0,
            "Stress": true, "DetectedStress": true,
            "MemBeginTime": 22100, "MemEndTime": 22280, "ReferenceLetter": "v" }
        ] },
      { "Word": "beach", "ReferenceWord": "beach",
        "PronAccuracy": 92.0, "MemBeginTime": 1800, "MemEndTime": 2400,
        "PhoneInfos": [ "…高分词同结构，略…" ] }
    ]
  }
}
```

（真实 API 中 `result` 为字符串需 parse；高分词同样返回完整结构。此为按文档字段构造的 mock，真实数值以实测为准。）

## 4. 产品形态

### 4.1 位置与出现规则

- 用户提交后**立即进入结果页**：先显示用户原话与反馈生成状态，不等完整 JSON；纠正完成后再上传录音并单独请求发音评测；
- `gaps[]` 是唯一纠正主体，每条把「你说的」放上方、「这样说」放下方；可覆盖短语或整句，不做字符级强行对齐；
- 发音卡不阻塞文字结果；请求中显示紧凑生成态，失败时明确说明不影响文字纠正，未配置供应商时不发起请求；
- gaps 核心对比默认展开；独立标准答案默认折叠，控制结果页长度；
- 一次最多 3 张词卡（多出的折叠为"还有 N 处"）；
- 深浅主题走语义 token 自动跟随；中英双文案走 useI18n。

### 4.2 词卡结构（对照 `pronunciation-card-demo.html`）

每张词卡：

1. 词 + 词分徽章；
2. 双栏对比：你的发音 IPA（警示色）vs 正确 IPA（绿色）；重音类问题改为"重音点"对比（大点=重读音节，期望 vs 实际）；
3. 一句人话解释（§2.3 归因链产出）；
4. 首版两个音频入口：「你的原音」（按时间戳 seek 现有 recordingUrl 回放，不新增音频文件）与「标准音」（TTS）。「再练一次」必须等单词录音、模式 0 复测与状态持久化闭环一起上线，不先放无效按钮。

demo 页中「标准音」用浏览器 speechSynthesis 模拟、「你的原音」为动画——**仅演示替身**；真实产品按上段实现。demo 其余区块（分数/三卡/差距卡）复刻真实样式，用于评审视觉。

### 4.3 「再练一次」单词闭环

后续阶段不跳页、卡内内联展开：

```
听标准音（TTS）→ 读这一个词（录 2–3 秒）→ 引擎模式 0 秒级评分
  → 过（≥80，可配）：标 ✅「已修复」，按钮变「再练 / 已修复」
  → 没过：更新对比（"这次 s 还是嘶音…"），再来一遍
```

- 对 sailor/seller 类加**最小对立对比练**：标准音连播两候选词，用户各跟读一遍，分别打分；
- 成本：模式 0 一次 = 1 计费单位 ≈ 0.004 元，练 10 遍 4 分钱；
- 练过的词记录进 `pronunciation.practiceLog`（次数/分数曲线），为后续错题本联动留数据。

## 5. 音素规则库（首发清单）

数据文件 `server/services/pronunciation/rules.json`，增补走代码审查。首发 16 组（对立 / 典型表现 / 教法 / 最小对立例词）：

| # | 对立 | 典型表现 | 教法（人写） | 例词 |
|---|---|---|---|---|
| 1 | /θ/→/s/ | think→sink | 舌尖轻抵上齿、气流从舌齿缝出，别用「思」的嘶音 | think/sink |
| 2 | /θ/→/f/ | three→free 类 | 舌尖在齿间，不是上齿咬下唇吹气 | three/free |
| 3 | /ð/→/z//d/ | they→zay | 位置同 th 但声带振动 | they/day |
| 4 | /v/→/w/ | very→wery | 上齿轻触下唇内侧摩擦，别圆唇成 w | very/wary |
| 5 | /l/↔/r/ | light→right | l 舌尖抵齿龈，r 舌尖后缩不接触 | light/right |
| 6 | /eɪ/→/ɛ/ | sailor→seller | /eɪ/ 是滑动音：嘴咧开起、向 i 收尾 | sailor/seller |
| 7 | /æ/→/e/ | bad→bed | 下颌再降一格、嘴张大 | bad/bed |
| 8 | /ɪ/→/iː/ | ship→sheep | /ɪ/ 短而松，/iː/ 长而紧、嘴角咧 | ship/sheep |
| 9 | /ʊ/→/uː/ | full→fool | /ʊ/ 短松，别拉长成 oo | full/fool |
| 10 | /ŋ/→/n/ 尾 | singing→sinnin | 舌根抵软腭、鼻腔共鸣，舌尖别前顶 | singing |
| 11 | 尾辅音丢失 | worl(d)、las(t) | 结尾轻收一个闭塞，别直接吞掉 | world/last |
| 12 | 尾辅音加元音 | and→and-uh | 干净收尾，别补「呃」 | and/ask |
| 13 | 词重音错位 | reCORD(动词)读成名词调 | 动词重音多在第二音节、名词多首音节，先重后轻 | record/REcord |
| 14 | 多音节重音错位 | comfortable 重音在第二音节 | 重音在首音节 COMF-，其余弱读 | comfortable |
| 15 | 弱读缺失 | to/and 全重读 | 功能词弱读成 /tə/ /ən/，节奏才像话 | to/and |
| 16 | /tʃ/→/ts/ | chair→tsair | 舌面抬起贴硬腭再放开，别用「茨」 | chair |

（重音/弱读类 13–15 由 `Stress/DetectedStress` 与流利度字段触发，非音素替换。）

## 6. 解释文案示例（输入 → 输出）

| 引擎事实 | 规则库 | LLM 输出 |
|---|---|---|
| three: det=s ref=th 分31 | #1 | 把 th 发成了「s」的嘶音。舌尖轻抵上齿、气流从舌齿缝出，别用「思」开头。 |
| sailor: det=eh ref=ey 分38，重音一致 | #6 | 重音位置对，但第一个元音像 /ɛ/，听着是 seller；正确 /eɪ/，嘴咧开滑动收尾。 |
| comfortable: 首音节 Stress=true/Detected=false | #14 | 重音应在首音节「COMF-」，你重读在了第二音节；先重后轻。 |
| very: det=w ref=v 分35 | #4 | v 要上齿碰下唇摩擦出声；你圆唇成了 w，very 听着像 wary。 |

## 7. 供应商路线与决策

| | 腾讯 SOE-N | 阿里云智能科教内容生成 | 科大讯飞 ISE / Suntone |
|---|---|---|---|
| 单词/音素/重音 | `Phone`/`ReferencePhone` 与 `Stress`/`DetectedStress` 同一公开契约 | 能做单词纠错、句子音素与重音，公开产品已确认 | 能做词/音素/重音，具体字段受 SKU 影响 |
| 成本 | 后付费 0.005 元/单位 | 按调用 0.004 元起，量大更低 | 公开包约 0.0054–0.006 元/次 |
| 现有供应商统一 | 新增供应商 | 与现有语音/对象存储统一 | 新增供应商 |
| 本界面适配度 | **最高**：实际/参考音素、实际/参考重音、时间戳直接成对 | 很接近，但字段分散在不同题型，授权链更长 | 能力够，购买前还要确认具体 SKU |

**首版选择腾讯，不是机械追求供应商数量最少。** 阿里云价格和统一性更好，若只看总分/词分会优先阿里；但本功能的核心是把「我实际发成什么」与「标准是什么」并排展示，腾讯模式 4 的公开字段更直接、实现和验收歧义更小。阿里云作为第二适配器候选：同一批真人录音若证明两者在误报、音素/重音可解释性和延迟上相当，则切回阿里云统一。

## 8. 接口与数据模型

### 8.1 provider 接缝

`server/services/pronunciation.py` 把供应商 WebSocket、签名、音频转换和字段归一化封装在服务端；路由和前端只认识统一 JSON。`PRONUNCIATION_PROVIDER` 是切换接缝，首版只实现 `tencent`，未知值会保持功能关闭，不会误用别家密钥。

### 8.2 HTTP 路由

- `POST /api/practice-sessions/{id}/attempts/{n}/pronunciation`：本轮 attempt 与录音已落库后触发；已有完成结果直接返回；
- 浏览器等待该请求的最终规范化 JSON，但它发生在结果页内部，不阻塞纠正主链路；供应商 WebSocket 原始流不透传浏览器；
- 上传录音响应携带 `pronunciationEnabled`，没有开关或密钥时前端不调用评测端点。

### 8.3 持久化（attempt.pronunciation）

```json
{
  "status": "completed",
  "provider": "tencent",
  "overallScore": 71.5,
  "accuracyScore": 69.0,
  "fluencyScore": 78.5,
  "completionScore": 100.0,
  "issues": [
    { "word": "three", "score": 42, "startMs": 9200, "endMs": 9750,
      "detectedIpa": "sriː", "referenceIpa": "θriː",
      "phones": [ { "detected": "s", "reference": "θ", "score": 31,
                    "stressExpected": false, "stressDetected": false,
                    "startMs": 0, "endMs": 180 } ],
      "coaching": "你更接近 /s/ → /θ/；先听标准音，再慢速跟读。" }
  ],
  "finishedAt": "…"
}
```

只存结构化结果与解释文案；**不新增原始音频副本**（回放用现有 `recordingUrl` + `startMs/endMs` seek）。

## 9. 成本（腾讯后付费口径，0.005 元/单位）

| 动作 | 单位 | 元 |
|---|---|---|
| 一次练习第一遍（≤40 词段落） | 2 | 0.010 |
| 3 个低分词二次纠错 | 3 | 0.015 |
| 「再练一次」单次（后续） | 1 | 0.005 |
| **一次练习含 3 词深挖** | **≈5** | **≈0.025** |

阿里云按调用 0.004 元起；是否改用阿里以同一真人录音 A/B 为准，不只按标价判断。

## 10. 隐私与合规

- 体验阶段只用**用户本人授权**的录音（确认用哪条或新录），不拿他人数据；
- 上线前更新隐私政策/麦克风说明：第三方处理披露、处理目的、不永久留存原始音频；
- 供应商密钥只放服务端，最小权限、可轮换；
- 腾讯与阿里云均可在境内处理；启用前仍要在隐私说明里披露新增的第三方音频处理目的。

## 11. 实施阶段

| 阶段 | 内容 | 前置 | 产出 |
|---|---|---|---|
| P1 集成骨架 | 结果页先进入、gap 短语/整句上下对照、折叠长内容、发音卡与持久化 | 无 | **已完成** |
| P2 腾讯适配 | WSS 签名、录音模式、两段式评测、字段归一化、feature flag | P1 | **已完成** |
| P3 体验启用 | 开通服务、配置独立最小权限生产身份并打开开关 | 账号开通+后付费 | **已完成，待用户真实录音体验** |
| P4 验收（可选） | 教师标注试点，按调研 §7 门槛判 | 录音+标注 | 验收报告 |

## 12. 未决与后续

未决：① 真人录音误报/延迟验证；② 是否补完整音素教法规则库；③ 只有腾讯出现质量、稳定性或成本问题时，是否启动阿里云同批对照并切回统一供应商。

后续延伸（首发不做）：错题本联动（未过词自动进复习队列）、教练自由点评（音频模型听韵律，需单独验证）、重音/弱读专项练习游戏化。
