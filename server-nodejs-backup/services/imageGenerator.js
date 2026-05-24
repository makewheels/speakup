const DASHSCOPE_URL =
  "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis";

const SCENE_PROMPTS = {
  daily: "A bright, photorealistic everyday life scene in a kitchen or dining room. Multiple people cooking, eating, or talking. Rich details: utensils, food, windows, plants. No text.",
  travel: "A bright, photorealistic travel scene at an airport check-in counter or hotel lobby. Travelers with luggage, staff at desks, information screens. No text.",
  nature: "A vibrant, photorealistic nature scene in a park or garden. People walking dogs, children playing, trees, flowers, birds. Clear actions visible. No text.",
  social: "A lively, photorealistic social scene at a restaurant or cafe. People chatting at tables, waiter serving, food and drinks on tables. Warm atmosphere. No text.",
  home: "A cozy, photorealistic home scene in a living room or bedroom. Family members relaxing, reading, playing. Furniture, books, lamps visible. No text.",
  city: "A bustling, photorealistic city scene: busy street with shops, pedestrians crossing, outdoor market stalls, bus or subway entrance. No text.",
};

const TOPICS = Object.keys(SCENE_PROMPTS);

async function pollTask(taskId, maxAttempts = 30) {
  const url = `https://dashscope.aliyuncs.com/api/v1/tasks/${taskId}`;
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise((r) => setTimeout(r, 2000));
    const res = await fetch(url, {
      headers: { Authorization: `Bearer ${process.env.DASHSCOPE_API_KEY}` },
    });
    const data = await res.json();
    const status = data.output?.task_status;
    if (status === "SUCCEEDED") {
      return data.output.results?.[0]?.url || "";
    }
    if (status === "FAILED") {
      throw new Error(data.output?.message || "Image generation failed");
    }
  }
  throw new Error("Image generation timed out");
}

async function generateOne(topic) {
  const t = topic || TOPICS[Math.floor(Math.random() * TOPICS.length)];
  const prompt = SCENE_PROMPTS[t];

  const res = await fetch(DASHSCOPE_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${process.env.DASHSCOPE_API_KEY}`,
      "X-DashScope-Async": "enable",
    },
    body: JSON.stringify({
      model: "wanx-v1",
      input: { prompt },
      parameters: { size: "1024*1024", n: 1 },
    }),
  });

  const data = await res.json();
  if (!res.ok || data.code) {
    throw new Error(data.message || "Image generation failed");
  }

  const taskId = data.output?.task_id;
  if (!taskId) throw new Error("No task ID returned");

  const imageUrl = await pollTask(taskId);
  return { imageUrl, topic: t, prompt };
}

// Image cache: userId -> { imageUrl, topic, prompt }
const imageCache = new Map();
// Pending prefetches: userId -> Promise
const pendingPrefetches = new Map();

export async function generateImage() {
  return generateOne();
}

export async function getNextImage(userId) {
  // Return cached image immediately
  const cached = imageCache.get(userId);
  if (cached) {
    imageCache.delete(userId);
    // Replenish cache in background
    startPrefetch(userId);
    return cached;
  }

  // No cache — check if prefetch is in progress
  const pending = pendingPrefetches.get(userId);
  if (pending) {
    await pending; // wait for prefetch to complete
    const cached = imageCache.get(userId);
    if (cached) {
      imageCache.delete(userId);
      startPrefetch(userId);
      return cached;
    }
  }

  // Generate synchronously (first time ever)
  const result = await generateOne();
  startPrefetch(userId);
  return result;
}

export function startPrefetch(userId) {
  if (pendingPrefetches.has(userId)) return; // already prefetching
  if (imageCache.has(userId)) return;        // already have one cached

  const promise = generateOne()
    .then((img) => {
      imageCache.set(userId, img);
    })
    .catch(() => {})
    .finally(() => {
      pendingPrefetches.delete(userId);
    });

  pendingPrefetches.set(userId, promise);
}
