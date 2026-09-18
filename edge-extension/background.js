async function extractCurrentJobPosting() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !tab.url) {
    throw new Error("Couldn't identify the active tab.");
  }
  if (!/^https?:/i.test(tab.url)) {
    throw new Error("Open a job posting on a normal website, then try again.");
  }

  await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    files: ["content.js"],
  });
  return chrome.tabs.sendMessage(tab.id, { type: "extract-job-posting" });
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "extract-current-job-posting") return;

  extractCurrentJobPosting()
    .then(sendResponse)
    .catch((error) => sendResponse({
      ok: false,
      error: error?.message || "Couldn't read this page. Try opening the job details first.",
    }));
  return true;
});
