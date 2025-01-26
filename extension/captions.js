let overlay = null;

// Listen for caption updates from background.js
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "updateCaption" && message.text) {
    if (!overlay) {
      // Create overlay
      overlay = document.createElement("div");
      overlay.style.position = "fixed";
      overlay.style.bottom = "20px";
      overlay.style.left = "20px";
      overlay.style.padding = "10px";
      overlay.style.backgroundColor = "rgba(0, 0, 0, 0.8)";
      overlay.style.color = "white";
      overlay.style.fontSize = "16px";
      overlay.style.borderRadius = "10px";
      overlay.style.zIndex = "10000";
      document.body.appendChild(overlay);
    }
    // Update caption text
    overlay.textContent = message.text;
  }
});
