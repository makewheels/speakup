import { Router } from "express";
import User from "../db/models/User.js";
import { startPrefetch } from "../services/imageGenerator.js";

const router = Router();

router.post("/login", async (req, res) => {
  try {
    const { phone } = req.body;
    if (!phone || !/^1\d{10}$/.test(phone)) {
      return res.status(400).json({ error: "请输入正确的手机号" });
    }

    let user = await User.findOne({ phone });
    if (!user) {
      user = await User.create({ phone, nickname: `用户${phone.slice(-4)}` });
    }
    user.lastLoginAt = new Date();
    await user.save();

    // Start pre-generating an image in background
    startPrefetch(user._id.toString());
    res.json({ userId: user._id, phone: user.phone, nickname: user.nickname });
  } catch (err) {
    res.status(500).json({ error: "登录失败" });
  }
});

export default router;
