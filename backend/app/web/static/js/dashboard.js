async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`HTTP ${res.status}: ${txt}`);
  }
  const payload = await res.json();
  if (payload && payload.success === false) {
    const msg = (payload.error && payload.error.message) ? payload.error.message : "Request failed";
    throw new Error(msg);
  }
  return payload && payload.data !== undefined ? payload.data : payload;
}

function initCourseCharts() {
  const resultsCanvas = document.getElementById("resultsChart");
  const emotionCanvas = document.getElementById("emotionChart");

  if (!resultsCanvas || !emotionCanvas) return;
  const courseId = resultsCanvas.dataset.courseId;

  fetchJson(`/dashboard/api/course/${courseId}/results`)
    .then((data) => {
      const summary = document.getElementById("resultsSummary");
      if (summary) {
        summary.textContent = `Accuracy: ${(data.accuracy * 100).toFixed(1)}% | Answers: ${data.total_answers} | Sessions: ${data.total_sessions}`;
      }

      new Chart(resultsCanvas, {
        type: "bar",
        data: {
          labels: ["Correct", "Incorrect"],
          datasets: [
            {
              label: "Answers",
              data: [data.correct_answers, data.total_answers - data.correct_answers],
              backgroundColor: ["#16a34a", "#ef4444"],
            },
          ],
        },
        options: { responsive: true, plugins: { legend: { display: false } } },
      });
    })
    .catch((e) => console.error(e));

  fetchJson(`/dashboard/api/course/${courseId}/emotion-summary`)
    .then((data) => {
      const labels = Object.keys(data.counts || {});
      const values = Object.values(data.counts || {});

      new Chart(emotionCanvas, {
        type: "doughnut",
        data: {
          labels,
          datasets: [
            {
              data: values,
              backgroundColor: ["#0ea5e9", "#22c55e", "#f59e0b", "#ef4444", "#a855f7"],
            },
          ],
        },
        options: { responsive: true },
      });
    })
    .catch((e) => console.error(e));
}

document.addEventListener("DOMContentLoaded", () => {
  initCourseCharts();
});
