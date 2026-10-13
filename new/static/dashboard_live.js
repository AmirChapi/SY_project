// מרענן את לוח "שיחות פעילות כרגע" בדשבורד באמצעות polling פשוט (בלי WebSocket)
(function () {
  const board = document.getElementById("active-calls-board");
  if (!board) return;

  const url = board.dataset.pollUrl;

  function levelColor(level) {
    if (level === "גבוה") return "#dc2626";
    if (level === "בינוני") return "#ca8a04";
    return "#16a34a";
  }

  function render(calls) {
    if (!calls.length) {
      board.innerHTML = '<p class="hint">אין שיחות פעילות כרגע.</p>';
      return;
    }

    board.innerHTML = "";
    calls.forEach((c) => {
      const color = levelColor(c.level);
      const card = document.createElement("a");
      card.href = c.url;
      card.className = "mini-call-card";
      card.style.borderInlineStartColor = color;
      card.innerHTML =
        "<strong>" + c.scenario_title + "</strong>" +
        "<div>" + c.customer_name + " | " + c.phone_display + "</div>" +
        "<div class='mini-score'>ציון: " + c.score + " (" + c.level + ") | " + c.elapsed + " שנ'</div>" +
        "<div class='mini-bar'><div class='mini-bar-fill' style='width:" + Math.min(c.score, 100) + "%; background:" + color + "'></div></div>";
      board.appendChild(card);
    });
  }

  async function poll() {
    try {
      const response = await fetch(url);
      if (response.ok) {
        const data = await response.json();
        render(data);
      }
    } catch (err) {
      console.error("שגיאה בעדכון לוח הבקרה:", err);
    }
    setTimeout(poll, 2000);
  }

  poll();
})();
