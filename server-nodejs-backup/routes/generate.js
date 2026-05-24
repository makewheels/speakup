import { Router } from "express";
import { getNextImage, startPrefetch } from "../services/imageGenerator.js";

const router = Router();

// Get next image: cached if available, else generate
router.post("/next", async (req, res) => {
  try {
    const { userId } = req.body;
    if (!userId) return res.status(400).json({ error: "Missing userId" });
    const result = await getNextImage(userId);
    res.json(result);
  } catch (err) {
    console.error("Image generation error:", err);
    res.status(500).json({ error: "图片生成失败" });
  }
});

// Prefetch: start generating in background
router.post("/prefetch", (req, res) => {
  const { userId } = req.body;
  if (!userId) return res.status(400).json({ error: "Missing userId" });
  startPrefetch(userId);
  res.json({ ok: true });
});

export default router;
