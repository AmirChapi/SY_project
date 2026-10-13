// מצייר שני תרשימי עמודות פשוטים (Canvas בלבד, ללא ספריות) עבור מסך ניתוח הדפוסים
(function () {
  const dataEl = document.getElementById("analytics-data");
  if (!dataEl) return;

  const data = JSON.parse(dataEl.textContent);

  function levelColor(level) {
    if (level === "גבוה") return "#dc2626";
    if (level === "בינוני") return "#ca8a04";
    return "#16a34a";
  }

  function drawBarChart(canvasId, items, labelKey, valueKey, colorFn) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    const maxValue = Math.max(1, ...items.map((item) => item[valueKey]));
    const paddingRight = 140; // מקום לתווית טקסט בעברית מימין (RTL)
    const chartWidth = w - paddingRight - 20;
    const barHeight = Math.min(36, (h - 20) / items.length - 10);
    const gap = (h - 20) / items.length;

    items.forEach((item, i) => {
      const y = 15 + i * gap;
      const barWidth = (item[valueKey] / maxValue) * chartWidth;

      ctx.fillStyle = "#f1f5f9";
      ctx.fillRect(10, y, chartWidth, barHeight);

      ctx.fillStyle = colorFn ? colorFn(item[labelKey]) : "#123456";
      ctx.fillRect(10, y, barWidth, barHeight);

      ctx.fillStyle = "#1f2933";
      ctx.font = "14px Arial";
      ctx.textAlign = "right";
      ctx.direction = "rtl";
      ctx.fillText(item[labelKey] + " (" + item[valueKey] + ")", w - 10, y + barHeight / 1.5);
    });
  }

  drawBarChart("risk-distribution-chart", data.risk_distribution, "level", "count", levelColor);
})();
