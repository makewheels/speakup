import { Router } from "express";
import { correctText } from "../services/corrector.js";
import Session from "../db/models/Session.js";

const router = Router();

router.post("/", async (req, res) => {
  try {
    const { userId, sessionId, text, sceneDescription } = req.body;

    if (!userId || !sessionId) {
      return res.status(400).json({ error: "缺少用户或会话信息" });
    }

    const session = await Session.findOne({ _id: sessionId, userId });
    if (!session) return res.status(404).json({ error: "会话不存在" });

    const result = await correctText({ text, sceneDescription });

    session.attempts.push({
      transcript: text,
      correctedText: result.correctedText,
      corrections: result.corrections,
      tips: result.tips,
      scores: result.scores,
    });
    await session.save();

    res.json({
      sessionId: session._id,
      attemptNumber: session.attempts.length,
      ...result,
    });
  } catch (err) {
    console.error("Correction error:", err);
    res.status(500).json({ error: "纠正失败" });
  }
});

export default router;
