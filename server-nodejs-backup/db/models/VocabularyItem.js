import mongoose from "mongoose";

const vocabSchema = new mongoose.Schema(
  {
    userId: { type: mongoose.Schema.Types.ObjectId, ref: "User", required: true, index: true },
    word: { type: String, required: true },
    chinese: { type: String, default: "" },
    contextSentence: { type: String, default: "" },
    sessionId: { type: mongoose.Schema.Types.ObjectId, ref: "Session" },
    nextReviewAt: { type: Date, default: Date.now },
    reviewCount: { type: Number, default: 0 },
    interval: { type: Number, default: 1 }, // days
    easiness: { type: Number, default: 2.5 },
  },
  { timestamps: true }
);

vocabSchema.index({ userId: 1, nextReviewAt: 1 });

export default mongoose.model("VocabularyItem", vocabSchema);
