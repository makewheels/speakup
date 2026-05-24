import mongoose from "mongoose";

const userSchema = new mongoose.Schema(
  {
    phone: { type: String, unique: true, required: true, index: true },
    nickname: { type: String, default: "" },
    lastLoginAt: { type: Date, default: Date.now },
  },
  { timestamps: true }
);

export default mongoose.model("User", userSchema);
