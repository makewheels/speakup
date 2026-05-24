import "./config.js";
import express from "express";
import cors from "cors";
import { connectDB } from "./db/connection.js";
import authRoutes from "./routes/auth.js";
import generateRoutes from "./routes/generate.js";
import correctRoutes from "./routes/correct.js";
import sessionRoutes from "./routes/sessions.js";
import vocabularyRoutes from "./routes/vocabulary.js";

const app = express();
app.use(cors());
app.use(express.json());

app.use("/api/auth", authRoutes);
app.use("/api/generate", generateRoutes);
app.use("/api/correct", correctRoutes);
app.use("/api/sessions", sessionRoutes);
app.use("/api/vocabulary", vocabularyRoutes);

const PORT = process.env.PORT || 3001;

connectDB().then(() => {
  app.listen(PORT, () => {
    console.log(`Server running on http://localhost:${PORT}`);
  });
});
