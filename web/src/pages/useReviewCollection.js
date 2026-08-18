import { useState } from "react";
import { useUser } from "../context/useUser.js";
import { useT } from "../i18n/useI18n.js";
import { api } from "../api/client.js";

// 错题本收录：gap 加入/取消（错题）+ 标准答案整句记笔记（好表达笔记 kind=note）
export function useReviewCollection(session, result) {
  const { user } = useUser();
  const t = useT();
  const [savedMap, setSavedMap] = useState({}); // gap 下标 -> reviewItem id（自动收录的初始就带，手动加/取消同步）
  const [noteSavedId, setNoteSavedId] = useState(""); // 标准答案「记为笔记」后的 reviewItem id

  const resetReviewCollection = () => {
    setSavedMap({});
    setNoteSavedId("");
  };

  // 收录 / 取消收录：点一下加入错题本，再点一下取消
  const toggleGap = async (g, i) => {
    if (!session?._id) return;
    const savedId = savedMap[i];
    if (savedId) {
      try {
        await api.deleteReviewItem(savedId, user.userId);
        setSavedMap((m) => { const n = { ...m }; delete n[i]; return n; });
      } catch (e) {
        alert(t("practice.removeFailed", { msg: e.message }));
      }
      return;
    }
    try {
      const { ids } = await api.addReviewItems(user.userId, [{
        expression: g.better,
        original: g.original,
        note: g.why,
        chinese: g.chinese || "",
        contextSentence: result?.nativeVersion || "",
        practiceId: session._id,
      }]);
      const id = ids?.[0];
      if (id) setSavedMap((m) => ({ ...m, [i]: id }));
    } catch (e) {
      alert(t("practice.addFailed", { msg: e.message }));
    }
  };

  // 标准答案整句记为「好表达笔记」（kind=note，与错题分开复习）；再点一下取消
  const toggleNote = async () => {
    if (!session?._id || !result?.standardAnswer) return;
    if (noteSavedId) {
      try {
        await api.deleteReviewItem(noteSavedId, user.userId);
        setNoteSavedId("");
      } catch (e) {
        alert(t("practice.removeFailed", { msg: e.message }));
      }
      return;
    }
    try {
      const { ids } = await api.addReviewItems(user.userId, [{
        expression: result.standardAnswer.trim(),
        kind: "note",
        practiceId: session._id,
      }]);
      const id = ids?.[0];
      if (id) setNoteSavedId(id);
    } catch (e) {
      alert(t("practice.addFailed", { msg: e.message }));
    }
  };

  return {
    savedMap,
    setSavedMap,
    noteSavedId,
    resetReviewCollection,
    toggleGap,
    toggleNote,
  };
}
