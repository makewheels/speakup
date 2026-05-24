import { Router } from "express";
import Session from "../db/models/Session.js";

const router = Router();

// Create session (after image generated)
router.post("/", async (req, res) => {
  try {
    const { userId, topic, sceneDescription, imageUrl, imagePrompt } = req.body;
    const session = await Session.create({
      userId,
      topic,
      sceneDescription,
      imageUrl,
      imagePrompt,
    });
    res.json(session);
  } catch (err) {
    res.status(500).json({ error: "创建会话失败" });
  }
});

// Get session detail
router.get("/:id", async (req, res) => {
  try {
    const session = await Session.findById(req.params.id);
    if (!session) return res.status(404).json({ error: "会话不存在" });
    res.json(session);
  } catch (err) {
    res.status(500).json({ error: "获取会话失败" });
  }
});

// List sessions for a user
router.get("/", async (req, res) => {
  try {
    const { userId, limit = 20, skip = 0 } = req.query;
    const sessions = await Session.find({ userId })
      .sort({ createdAt: -1 })
      .skip(Number(skip))
      .limit(Number(limit))
      .select("topic imageUrl attempts createdAt");
    res.json(sessions);
  } catch (err) {
    res.status(500).json({ error: "获取历史失败" });
  }
});

export default router;
