(() => {
  const messagesEl = document.getElementById("messages");
  const formEl = document.getElementById("input-form");
  const inputEl = document.getElementById("input-field");
  const sendBtn = document.getElementById("send-btn");
  const homeBtn = document.getElementById("home-link");
  const faqBtn = document.getElementById("faq-btn");
  const feedbackBtn = document.getElementById("feedback-btn");

  // session_id намеренно не переиспользуется между перезагрузками страницы:
  // если сохранённая сессия застряла в середине визарда (flow_state), а
  // визард не имеет аварийного выхода (решение Plan-web-ui.md), автозапрос
  // "services" при загрузке интерпретировался бы как невалидный ответ на
  // текущий шаг — пользователь получал ошибку без возможности из неё выйти.
  // Каждая загрузка страницы начинает новую сессию, mode="main_menu" гарантированно.
  let sessionId = null;
  let currentMode = "main_menu";

  function addBotTurn(reply, buttons, isError, faqItems) {
    const turn = document.createElement("div");
    turn.className = "turn turn--bot";

    if (faqItems) {
      const faq = document.createElement("div");
      faq.className = "faq";
      for (const item of faqItems) {
        const details = document.createElement("details");
        details.className = "faq__item";
        const summary = document.createElement("summary");
        summary.textContent = item.title;
        const body = document.createElement("div");
        body.className = "faq__body";
        body.textContent = item.body;
        details.appendChild(summary);
        details.appendChild(body);
        faq.appendChild(details);
      }
      turn.appendChild(faq);
    } else {
      const bubble = document.createElement("div");
      bubble.className = "bubble" + (isError ? " is-error" : "");
      bubble.textContent = reply;
      turn.appendChild(bubble);
    }

    if (buttons && buttons.length) {
      const buttonsEl = document.createElement("div");
      buttonsEl.className = "turn__buttons";
      for (const button of buttons) {
        const btn = document.createElement("button");
        btn.className = "btn";
        btn.type = "button";
        btn.textContent = button.label;
        btn.addEventListener("click", () => sendInput(button.value, btn));
        buttonsEl.appendChild(btn);
      }
      turn.appendChild(buttonsEl);
    }

    messagesEl.appendChild(turn);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function addUserTurn(text) {
    const turn = document.createElement("div");
    turn.className = "turn turn--user";
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = text;
    turn.appendChild(bubble);
    messagesEl.appendChild(turn);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function setLoading(loading) {
    sendBtn.disabled = loading;
    sendBtn.classList.toggle("is-loading", loading);
    homeBtn.disabled = loading || currentMode !== "main_menu";
    faqBtn.disabled = loading;
    feedbackBtn.disabled = loading;
    document.querySelectorAll(".turn__buttons .btn").forEach((btn) => {
      btn.disabled = loading;
      btn.classList.remove("is-loading");
    });
  }

  async function sendInput(value, triggeringButton) {
    setLoading(true);
    if (triggeringButton) {
      triggeringButton.classList.add("is-loading");
    }

    let data;
    try {
      const resp = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, input: value }),
      });
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`);
      }
      data = await resp.json();
    } catch (err) {
      addBotTurn(
        "Не удалось отправить запрос. Проверьте соединение и попробуйте ещё раз.",
        [{ label: "Повторить", value: value }],
        true,
        null
      );
      setLoading(false);
      return;
    }

    sessionId = data.session_id;
    currentMode = data.mode;

    addBotTurn(data.reply, data.buttons, data.is_error, data.faq);
    setLoading(false);
  }

  formEl.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = inputEl.value.trim();
    if (!text) {
      return;
    }
    addUserTurn(text);
    inputEl.value = "";
    sendInput(text);
  });

  homeBtn.addEventListener("click", () => {
    if (currentMode !== "main_menu") {
      return;
    }
    sendInput("services");
  });

  faqBtn.addEventListener("click", () => sendInput("faq"));
  feedbackBtn.addEventListener("click", () => sendInput("feedback"));

  // Стартовый экран
  sendInput("services");
})();
