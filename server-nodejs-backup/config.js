import dotenv from "dotenv";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const envFile = `.env.${process.env.NODE_ENV || "development"}`;
dotenv.config({ path: path.join(__dirname, envFile) });
// Fallback to .env
dotenv.config({ path: path.join(__dirname, ".env"), override: false });
