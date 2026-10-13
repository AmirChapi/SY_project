// JavaScript פשוט - מחשב רמת סיכון חיה בטופס פתיחת שיחה, ללא רענון עמוד
document.addEventListener("DOMContentLoaded", () => {
  const checkboxes = document.querySelectorAll(".indicator-checkbox");
  const scoreValue = document.getElementById("score-value");
  const scoreLevel = document.getElementById("score-level");

  if (!checkboxes.length || !scoreValue || !scoreLevel) {
    return;
  }

  async function updateLiveScore() {
    const payload = {};
    checkboxes.forEach((cb) => {
      payload[cb.dataset.key] = cb.checked;
    });

    try {
      const response = await fetch("/api/score", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      scoreValue.textContent = result.score;
      scoreLevel.textContent = result.level;
    } catch (err) {
      console.error("שגיאה בחישוב הסיכון:", err);
    }
  }

  checkboxes.forEach((cb) => cb.addEventListener("change", updateLiveScore));
});
