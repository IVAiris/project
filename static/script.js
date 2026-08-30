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

  // Кнопки/поля активны только под самым последним сообщением — как только
  // рендерится новый раунд диалога, элементы предыдущего раунда навсегда
  // блокируются (не просто временно на время запроса, как раньше).
  let activeInteractive = null;

  function lockActiveInteractive() {
    if (!activeInteractive) return;
    activeInteractive.querySelectorAll("button, input, textarea").forEach((el) => {
      el.disabled = true;
    });
  }

  function buildButtonsEl(buttons, onClick) {
    const wrap = document.createElement("div");
    wrap.className = "turn__buttons";
    for (const button of buttons) {
      const btn = document.createElement("button");
      btn.className = "btn" + (button.wide ? " btn--wide" : "");
      if (button.is_active) {
        btn.classList.add("is-active");
      }
      if (button.is_back) {
        btn.classList.add("btn--back");
      }
      btn.type = "button";
      btn.textContent = button.label;
      btn.addEventListener("click", () => onClick(button.value, btn));
      wrap.appendChild(btn);
    }
    return wrap;
  }

  function openOverlay(title, body) {
    const overlay = document.createElement("div");
    overlay.className = "overlay";
    const panel = document.createElement("div");
    panel.className = "overlay__panel";
    const heading = document.createElement("h2");
    heading.className = "overlay__title";
    heading.textContent = title;
    const text = document.createElement("div");
    text.className = "overlay__body";
    text.textContent = body;
    const closeBtn = document.createElement("button");
    closeBtn.className = "btn overlay__close";
    closeBtn.type = "button";
    closeBtn.textContent = "Закрыть";
    closeBtn.addEventListener("click", () => overlay.remove());
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) overlay.remove();
    });
    panel.appendChild(heading);
    panel.appendChild(text);
    panel.appendChild(closeBtn);
    overlay.appendChild(panel);
    document.body.appendChild(overlay);
  }

  function buildFaqGrid(items) {
    const grid = document.createElement("div");
    grid.className = "faq-grid";
    for (const item of items) {
      const btn = document.createElement("button");
      btn.className = "btn";
      btn.type = "button";
      btn.textContent = item.title;
      btn.addEventListener("click", () => openOverlay(item.title, item.body));
      grid.appendChild(btn);
    }
    return grid;
  }

  function buildFeedbackForm() {
    const wrap = document.createElement("div");
    wrap.className = "form";

    const fields = [
      { key: "contact_name", label: "Укажите, как к Вам обращаться", type: "text" },
      { key: "contact_email", label: "Укажите Вашу эл. почту", type: "email" },
      { key: "message_text", label: "Введите Ваш отзыв здесь", type: "textarea" },
    ];

    const inputs = {};
    const errorEls = {};

    for (const field of fields) {
      const fieldWrap = document.createElement("div");
      fieldWrap.className = "form__field";
      const label = document.createElement("label");
      label.textContent = field.label;
      const input =
        field.type === "textarea" ? document.createElement("textarea") : document.createElement("input");
      if (field.type !== "textarea") {
        input.type = field.type;
      }
      input.className = "form__input";
      const errorEl = document.createElement("div");
      errorEl.className = "form__error";
      fieldWrap.appendChild(label);
      fieldWrap.appendChild(input);
      fieldWrap.appendChild(errorEl);
      wrap.appendChild(fieldWrap);
      inputs[field.key] = input;
      errorEls[field.key] = errorEl;
    }

    const actions = document.createElement("div");
    actions.className = "turn__buttons";
    const backBtn = document.createElement("button");
    backBtn.className = "btn btn--back";
    backBtn.type = "button";
    backBtn.textContent = "Вернуться на предыдущий экран";
    backBtn.addEventListener("click", () => sendInput("services"));
    const submitBtn = document.createElement("button");
    submitBtn.className = "btn";
    submitBtn.type = "button";
    submitBtn.textContent = "Отправить";
    actions.appendChild(backBtn);
    actions.appendChild(submitBtn);
    wrap.appendChild(actions);

    submitBtn.addEventListener("click", async () => {
      for (const el of Object.values(errorEls)) {
        el.textContent = "";
      }
      submitBtn.disabled = true;
      submitBtn.classList.add("is-loading");

      const payload = {
        contact_name: inputs.contact_name.value,
        contact_email: inputs.contact_email.value,
        message_text: inputs.message_text.value,
      };

      let data;
      try {
        const resp = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId, input: "feedback_submit", payload }),
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        data = await resp.json();
      } catch (err) {
        addBotTurn(
          "Ошибка отправки. Попробуйте повторить ввод через пару минут.",
          [],
          true,
          null
        );
        submitBtn.disabled = false;
        submitBtn.classList.remove("is-loading");
        return;
      }

      sessionId = data.session_id;
      currentMode = data.mode;
      submitBtn.disabled = false;
      submitBtn.classList.remove("is-loading");

      if (data.is_error && data.form_errors) {
        for (const [key, message] of Object.entries(data.form_errors)) {
          if (errorEls[key]) errorEls[key].textContent = message;
        }
        return; // введённые данные остаются в полях — не сбрасываем форму
      }

      wrap.remove();
      addBotTurn(data.reply, data.buttons, data.is_error, data.faq);
    });

    return wrap;
  }

  function addBotTurn(reply, buttons, isError, faqItems, form) {
    const turn = document.createElement("div");
    turn.className = "turn turn--bot";

    if (form === "feedback") {
      const bubble = document.createElement("div");
      bubble.className = "bubble";
      bubble.textContent = reply;
      turn.appendChild(bubble);
      turn.appendChild(buildFeedbackForm());
    } else if (faqItems) {
      const bubble = document.createElement("div");
      bubble.className = "bubble";
      bubble.textContent = reply;
      turn.appendChild(bubble);
      turn.appendChild(buildFaqGrid(faqItems));
    } else {
      const bubble = document.createElement("div");
      bubble.className = "bubble" + (isError ? " is-error" : "");
      bubble.textContent = reply;
      turn.appendChild(bubble);
    }

    if (buttons && buttons.length) {
      turn.appendChild(buildButtonsEl(buttons, sendInput));
    }

    messagesEl.appendChild(turn);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    activeInteractive = turn;
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
  }

  async function sendInput(value, triggeringButton) {
    // Раунд начался — кнопки/поля предыдущего сообщения блокируются навсегда,
    // не только на время этого запроса (раньше все прошлые раунды разом
    // включались обратно после каждого ответа — исправленный баг).
    lockActiveInteractive();
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
        null,
        null
      );
      setLoading(false);
      return;
    }

    sessionId = data.session_id;
    currentMode = data.mode;

    addBotTurn(data.reply, data.buttons, data.is_error, data.faq, data.form);
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
