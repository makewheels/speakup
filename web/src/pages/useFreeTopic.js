import { useCallback, useRef, useState } from "react";
import { api } from "../api/client.js";

/**
 * 自由说话题状态：抽一个该用户没说过的话题（池子用完后端自动补题）。
 * loadTopic 带回流去重：已有话题/正在抽时不重复发请求（navigate 回流会二次触发 effect）。
 */
export default function useFreeTopic(userId) {
  const [freeTopic, setFreeTopic] = useState(null);
  const topicRef = useRef(null);     // freeTopic 镜像：effect 回流里读，避免闭包拿旧 state
  const loadingRef = useRef(false);  // 抽题进行中：并发去重

  const loadTopic = useCallback(async () => {
    if (loadingRef.current) return topicRef.current;
    loadingRef.current = true;
    try {
      const topic = await api.nextFreeTopic(userId);
      topicRef.current = topic;
      setFreeTopic(topic);
      return topic;
    } finally {
      loadingRef.current = false;
    }
  }, [userId]);

  const clearTopic = useCallback(() => {
    topicRef.current = null;
    setFreeTopic(null);
  }, []);

  const hasTopic = useCallback(() => Boolean(topicRef.current), []);

  return { freeTopic, setFreeTopic, loadTopic, clearTopic, hasTopic };
}
