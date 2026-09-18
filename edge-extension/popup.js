const statusEl = document.getElementById("status");
const extractButton = document.getElementById("extract");
const resultEl = document.getElementById("result");
const summaryEl = document.getElementById("summary");
const recordEl = document.getElementById("record");
const copyButton = document.getElementById("copy");

let currentRecord = "";

function setStatus(message) {
  statusEl.textContent = message;
}

extractButton.addEventListener("click", async () => {
  extractButton.disabled = true;
  resultEl.hidden = true;
  setStatus("Reading the current job posting…");
  try {
    const response = await chrome.runtime.sendMessage({ type: "extract-current-job-posting" });
    if (!response?.ok) throw new Error(response?.error || "Couldn't read this job posting.");

    currentRecord = JSON.stringify(response.job, null, 2);
    recordEl.value = currentRecord;
    summaryEl.textContent = `${response.job.title} at ${response.job.company}`;
    setStatus("Ready to copy. The full source text is retained in raw_description.");
    resultEl.hidden = false;
  } catch (error) {
    setStatus(error?.message || "Couldn't read this job posting.");
  } finally {
    extractButton.disabled = false;
  }
});

copyButton.addEventListener("click", async () => {
  if (!currentRecord) return;
  try {
    await navigator.clipboard.writeText(currentRecord);
    copyButton.textContent = "Copied";
  } catch {
    recordEl.focus();
    recordEl.select();
    copyButton.textContent = "Select JSON to copy";
  }
  setTimeout(() => { copyButton.textContent = "Copy JSON"; }, 1600);
});

document.getElementById("openApp").addEventListener("click", () => {
  chrome.tabs.create({ url: "http://localhost:8080" });
});
