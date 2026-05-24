import { Router } from "express";
import VocabularyItem from "../db/models/VocabularyItem.js";

const router = Router();

// Add words to vocabulary
router.post("/", async (req, res) => {
  try {
    const { userId, words } = req.body;
    // words: [{ word, chinese, contextSentence, sessionId }]

    const created = [];
    for (const w of words) {
      const existing = await VocabularyItem.findOne({ userId, word: w.word });
      if (existing) continue;
      const item = await VocabularyItem.create({
        userId,
        word: w.word,
        chinese: w.chinese || "",
        contextSentence: w.contextSentence || "",
        sessionId: w.sessionId,
      });
      created.push(item);
    }
    res.json({ added: created.length });
  } catch (err) {
    res.status(500).json({ error: "添加生词失败" });
  }
});

// List vocabulary
router.get("/", async (req, res) => {
  try {
    const { userId, due } = req.query;
    const filter = { userId };
    if (due === "true") {
      filter.nextReviewAt = { $lte: new Date() };
    }
    const items = await VocabularyItem.find(filter).sort({ nextReviewAt: 1 });
    res.json(items);
  } catch (err) {
    res.status(500).json({ error: "获取生词失败" });
  }
});

// Review a word
router.post("/:id/review", async (req, res) => {
  try {
    const { remembered } = req.body; // true or false
    const item = await VocabularyItem.findById(req.params.id);
    if (!item) return res.status(404).json({ error: "生词不存在" });

    item.reviewCount += 1;
    if (remembered) {
      item.easiness = Math.min(3, item.easiness + 0.1);
      item.interval = Math.round(item.interval * item.easiness);
    } else {
      item.easiness = Math.max(1.3, item.easiness - 0.3);
      item.interval = 1;
    }
    item.nextReviewAt = new Date(Date.now() + item.interval * 24 * 60 * 60 * 1000);
    await item.save();

    res.json(item);
  } catch (err) {
    res.status(500).json({ error: "复习失败" });
  }
});

// Delete a vocabulary item
router.delete("/:id", async (req, res) => {
  try {
    await VocabularyItem.findByIdAndDelete(req.params.id);
    res.json({ ok: true });
  } catch (err) {
    res.status(500).json({ error: "删除失败" });
  }
});

export default router;
