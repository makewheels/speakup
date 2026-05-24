import mongoose from "mongoose";

const correctionSchema = new mongoose.Schema(
  {
    original: String,
    corrected: String,
    reason: String,
  },
  { _id: false }
);

const attemptSchema = new mongoose.Schema(
  {
    transcript: { type: String, required: true },
    correctedText: String,
    corrections: [correctionSchema],
    tips: [String],
    scores: {
      grammar: { type: Number, min: 1, max: 5 },
      vocabulary: { type: Number, min: 1, max: 5 },
      completeness: { type: Number, min: 1, max: 5 },
      fluency: { type: Number, min: 1, max: 5 },
      structure: { type: Number, min: 1, max: 5 },
    },
  },
  { timestamps: true }
);

const sessionSchema = new mongoose.Schema(
  {
    userId: { type: mongoose.Schema.Types.ObjectId, ref: "User", required: true, index: true },
    topic: { type: String, required: true },
    sceneDescription: String,
    imageUrl: String,
    imagePrompt: String,
    attempts: [attemptSchema],
  },
  { timestamps: true }
);

export default mongoose.model("Session", sessionSchema);
