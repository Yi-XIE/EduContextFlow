const messagesEl = document.getElementById("messages");
const fileInput = document.getElementById("fileInput");
const fileList = document.getElementById("fileList");
const imagePreview = document.getElementById("imagePreview");
const textInput = document.getElementById("textInput");
const sendBtn = document.getElementById("sendBtn");

const state = {
  files: [],
};

function addMessage(role, text) {
  const div = document.createElement("div");
  div.className = `message ${role}`;
  div.textContent = text;
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

let loadingTimer = null;

function showLoading() {
  const loadingDiv = document.createElement("div");
  loadingDiv.className = "loading-message";
  loadingDiv.id = "loading-indicator";
  
  const textSpan = document.createElement("span");
  textSpan.textContent = "正在思考";
  
  const dotsDiv = document.createElement("div");
  dotsDiv.className = "loading-dots";
  
  for (let i = 0; i < 3; i++) {
    const dot = document.createElement("span");
    dotsDiv.appendChild(dot);
  }
  
  const timerSpan = document.createElement("span");
  timerSpan.id = "loading-timer";
  timerSpan.style.marginLeft = "8px";
  timerSpan.style.color = "#888";
  timerSpan.style.fontSize = "12px";
  timerSpan.textContent = "0s";
  
  loadingDiv.appendChild(textSpan);
  loadingDiv.appendChild(dotsDiv);
  loadingDiv.appendChild(timerSpan);
  messagesEl.appendChild(loadingDiv);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  
  // 启动计时器
  let seconds = 0;
  loadingTimer = setInterval(() => {
    seconds++;
    const timerEl = document.getElementById("loading-timer");
    if (timerEl) {
      timerEl.textContent = `${seconds}s`;
    }
  }, 1000);
  
  return loadingDiv;
}

function hideLoading() {
  const loadingDiv = document.getElementById("loading-indicator");
  if (loadingDiv) {
    loadingDiv.remove();
  }
  
  // 清除计时器
  if (loadingTimer) {
    clearInterval(loadingTimer);
    loadingTimer = null;
  }
}

function renderOptions(options) {
  if (!options || options.length === 0) return;
  const wrapper = document.createElement("div");
  wrapper.className = "message assistant";

  const title = document.createElement("div");
  title.textContent = "请选择：";
  wrapper.appendChild(title);

  const optionsRow = document.createElement("div");
  optionsRow.style.display = "flex";
  optionsRow.style.flexWrap = "wrap";
  optionsRow.style.gap = "8px";
  optionsRow.style.marginTop = "8px";

  options.forEach((option) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = option;
    button.style.padding = "6px 12px";
    button.style.borderRadius = "999px";
    button.style.border = "1px solid #d6dbe6";
    button.style.background = "#ffffff";
    button.style.cursor = "pointer";
    button.addEventListener("click", () => {
      textInput.value = option;
      sendMessage();
    });
    optionsRow.appendChild(button);
  });

  wrapper.appendChild(optionsRow);
  messagesEl.appendChild(wrapper);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function renderFiles() {
  fileList.innerHTML = "";
  imagePreview.innerHTML = "";
  state.files.forEach((file) => {
    const chip = document.createElement("div");
    chip.className = "file-chip";
    chip.textContent = `${file.name} (${Math.round(file.size / 1024)} KB)`;
    fileList.appendChild(chip);

    if (file.type.startsWith("image/")) {
      const img = document.createElement("img");
      img.alt = file.name;
      img.src = URL.createObjectURL(file);
      imagePreview.appendChild(img);
    }
  });
}

fileInput.addEventListener("change", (event) => {
  const files = Array.from(event.target.files || []);
  if (files.length === 0) return;
  state.files = files;
  renderFiles();
});

async function sendMessage() {
  const text = textInput.value.trim();
  if (!text && state.files.length === 0) {
    return;
  }

  addMessage("user", text || "[发送了文件]");
  textInput.value = "";
  sendBtn.disabled = true;
  
  // 显示加载动画
  showLoading();

  try {
    const formData = new FormData();
    formData.append("message", text);
    state.files.forEach((file) => {
      formData.append("files", file);
    });

    const response = await fetch("/api/chat", {
      method: "POST",
      body: formData,
    });

    // 隐藏加载动画
    hideLoading();
    
    if (!response.ok) {
      const errorData = await response.json();
      addMessage("assistant", `错误: ${errorData.error || "请求失败"}`);
      sendBtn.disabled = false;
      return;
    }

    const data = await response.json();
    const replyText = (data.reply || "").trim();
    const shouldRenderWrapper =
      replyText.length > 0 ||
      (data.output_files && data.output_files.length > 0);
    const replyWrapper = document.createElement("div");
    replyWrapper.className = "message assistant";
    if (replyText.length > 0) {
      replyWrapper.textContent = replyText;
    }
    if (shouldRenderWrapper) {
      messagesEl.appendChild(replyWrapper);
    }

    // 如果有输出文件，把“原文 + 查看输出”放在回复下方
    if (data.output_files && data.output_files.length > 0) {
      data.output_files.forEach(async (file) => {
        const link = document.createElement("a");
        link.href = `/${file}`;
        link.target = "_blank";
        link.textContent = `查看输出: ${file}`;
        link.style.display = "block";
        link.style.marginTop = "8px";
        link.style.color = "#007bff";

        // 图片直接预览
        if (file.endsWith(".png") || file.endsWith(".jpg") || file.endsWith(".jpeg")) {
          const img = document.createElement("img");
          img.src = `/${file}`;
          img.alt = file;
          img.style.maxWidth = "100%";
          img.style.borderRadius = "8px";
          img.style.marginTop = "8px";
          if (shouldRenderWrapper) {
            replyWrapper.appendChild(img);
          } else {
            messagesEl.appendChild(img);
          }
        }

        // 仅对文本类输出显示原文
        if (file.endsWith(".md") || file.endsWith(".txt")) {
          try {
            const fileResp = await fetch(`/${file}`);
            const content = await fileResp.text();
            const pre = document.createElement("pre");
            pre.textContent = content;
            pre.style.whiteSpace = "pre-wrap";
            pre.style.background = "#f7f7f7";
            pre.style.padding = "8px";
            pre.style.borderRadius = "8px";
            pre.style.marginTop = "8px";
            replyWrapper.appendChild(pre);
          } catch (err) {
            const warn = document.createElement("div");
            warn.textContent = "无法加载输出原文。";
            warn.style.marginTop = "8px";
            replyWrapper.appendChild(warn);
          }
        }

        if (shouldRenderWrapper) {
          replyWrapper.appendChild(link);
        } else {
          messagesEl.appendChild(link);
        }
      });
    }

    messagesEl.scrollTop = messagesEl.scrollHeight;

    // 清空文件
    state.files = [];
    fileInput.value = "";
    renderFiles();

    if (data.options && Array.isArray(data.options)) {
      renderOptions(data.options);
    }
  } catch (err) {
    hideLoading();
    addMessage("assistant", `网络错误: ${err.message}`);
  }

  sendBtn.disabled = false;
}

sendBtn.addEventListener("click", sendMessage);
textInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
});
