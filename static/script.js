const chatWindow = document.getElementById("chat-window");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const moodBadge = document.getElementById("mood-badge");
const resetBtn = document.getElementById("reset-btn");
const voiceToggle = document.getElementById("voice-toggle");

function addMessage(text, who) {
  const msg = document.createElement("div");
  msg.className = `msg ${who}`;
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;
  msg.appendChild(bubble);
  chatWindow.appendChild(msg);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function setMood(mood) {
  moodBadge.textContent = mood;
  moodBadge.className = `mood-badge ${mood}`;
}

function speak(text) {
  if (!voiceToggle.checked || !("speechSynthesis" in window)) return;
  const utter = new SpeechSynthesisUtterance(text);
  utter.rate = 0.95;
  utter.pitch = 0.8; // a little gruffer
  window.speechSynthesis.cancel(); // don't overlap
  window.speechSynthesis.speak(utter);
}

chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = chatInput.value.trim();
  if (!text) return;

  addMessage(text, "user");
  chatInput.value = "";

  const thinkingBubble = document.createElement("div");
  thinkingBubble.className = "msg tony";
  thinkingBubble.innerHTML = '<div class="bubble">...</div>';
  chatWindow.appendChild(thinkingBubble);
  chatWindow.scrollTop = chatWindow.scrollHeight;

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });
    const data = await res.json();
    thinkingBubble.remove();

    if (data.error) {
      addMessage(`(Something went wrong: ${data.error})`, "tony");
      return;
    }

    addMessage(data.reply, "tony");
    setMood(data.mood);
    speak(data.reply);
  } catch (err) {
    thinkingBubble.remove();
    addMessage("(Connection trouble. Try again in a sec.)", "tony");
  }
});

resetBtn.addEventListener("click", async () => {
  await fetch("/api/reset", { method: "POST" });
  chatWindow.innerHTML = "";
  addMessage("Alright, clean slate. Whaddya need?", "tony");
  setMood("calm");
});